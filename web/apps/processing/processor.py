"""Cliente HTTP do processador Java (leitura de PDF/DOCX, capa e HTML de leitura)."""

import httpx
from django.conf import settings


class ProcessorError(Exception):
    """Falha passageira (rede, processador fora do ar, sem vaga): vale tentar de novo."""


class DocumentRejected(Exception):
    """O arquivo não pode ser lido (senha, corrompido, formato): tentar de novo não adianta."""


def process(document, cover_width: int = 480, transport: httpx.BaseTransport | None = None) -> dict:
    payload = {
        "source": f"{document.relative_folder}/original.{document.kind}",
        "kind": document.kind,
        "output_dir": document.relative_folder,
        "cover_width": cover_width,
    }
    try:
        with httpx.Client(base_url=settings.PROCESSOR_URL, timeout=settings.PROCESSOR_TIMEOUT, transport=transport) as c:
            response = c.post("/v1/process", json=payload)
    except httpx.HTTPError as exc:
        raise ProcessorError(f"Processador indisponível: {exc}") from exc
    if response.status_code == 200:
        return response.json()
    try:
        body = response.json()
    except ValueError:
        body = {"message": response.text[:300]}
    message = body.get("message") or body.get("error") or f"HTTP {response.status_code}"
    if response.status_code in (400, 403, 404, 422):
        raise DocumentRejected(message)
    raise ProcessorError(f"Processador respondeu {response.status_code}: {message}")


def health(transport: httpx.BaseTransport | None = None) -> dict:
    try:
        with httpx.Client(base_url=settings.PROCESSOR_URL, timeout=3, transport=transport) as client:
            response = client.get("/health")
            response.raise_for_status()
            return {"online": True, **response.json()}
    except (httpx.HTTPError, ValueError) as exc:
        return {"online": False, "error": str(exc)[:200]}
