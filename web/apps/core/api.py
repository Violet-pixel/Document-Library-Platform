from rest_framework import status
from rest_framework.exceptions import APIException
from rest_framework.pagination import PageNumberPagination
from rest_framework.response import Response
from rest_framework.views import exception_handler as drf_exception_handler

MESSAGES = {
    "not_authenticated": "Entre na sua conta para continuar.",
    "authentication_failed": "Credenciais inválidas.",
    "permission_denied": "Você não tem permissão para esta ação.",
    "not_found": "Não encontrado.",
    "method_not_allowed": "Método não permitido.",
    "throttled": "Muitas tentativas. Aguarde um pouco e tente de novo.",
    "unsupported_media_type": "Formato de envio não suportado.",
    "parse_error": "Corpo da requisição inválido.",
}


def exception_handler(exc, context):
    response = drf_exception_handler(exc, context)
    if response is None:
        return None
    code = getattr(exc, "default_code", "error")
    if isinstance(exc, APIException):
        codes = exc.get_codes()
        if isinstance(codes, str):
            code = codes
    data = response.data
    if isinstance(data, dict) and "detail" in data and len(data) == 1:
        message = MESSAGES.get(code, str(data["detail"]))
        response.data = {"error": code, "message": message}
    elif response.status_code == status.HTTP_400_BAD_REQUEST:
        response.data = {"error": "invalid", "message": first_message(data), "fields": data}
    return response


def first_message(data) -> str:
    if isinstance(data, dict):
        for value in data.values():
            return first_message(value)
    if isinstance(data, list) and data:
        return first_message(data[0])
    return str(data) if data else "Dados inválidos."


class ApiError(APIException):
    status_code = 400
    default_code = "invalid"

    def __init__(self, message: str, code: str = "invalid", status_code: int = 400):
        super().__init__(detail=message, code=code)
        self.status_code = status_code


class Pagination(PageNumberPagination):
    page_size = 48
    page_size_query_param = "page_size"
    max_page_size = 200

    def get_paginated_response(self, data):
        return Response(
            {
                "count": self.page.paginator.count,
                "page": self.page.number,
                "pages": self.page.paginator.num_pages,
                "next": self.page.next_page_number() if self.page.has_next() else None,
                "results": data,
            }
        )

    def get_paginated_response_schema(self, schema):
        return {
            "type": "object",
            "properties": {
                "count": {"type": "integer"},
                "page": {"type": "integer"},
                "pages": {"type": "integer"},
                "next": {"type": "integer", "nullable": True},
                "results": schema,
            },
        }
