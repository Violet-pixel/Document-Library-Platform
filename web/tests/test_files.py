from django.test import RequestFactory

from apps.core.files import file_response


def respond(tmp_path, **headers):
    path = tmp_path / "arquivo.bin"
    if not path.exists():
        path.write_bytes(bytes(range(256)) * 4)
    return file_response(RequestFactory().get("/", **headers), path, "application/octet-stream")


def test_if_none_match_accepts_lists_weak_tags_and_wildcard(tmp_path):
    etag = respond(tmp_path)["ETag"]
    assert respond(tmp_path, HTTP_IF_NONE_MATCH=etag).status_code == 304
    assert respond(tmp_path, HTTP_IF_NONE_MATCH=f'"outro", W/{etag}').status_code == 304
    assert respond(tmp_path, HTTP_IF_NONE_MATCH="*").status_code == 304
    assert respond(tmp_path, HTTP_IF_NONE_MATCH='"outro"').status_code == 200


def test_range_without_numbers_is_ignored(tmp_path):
    response = respond(tmp_path, HTTP_RANGE="bytes=-")
    assert response.status_code == 200 and "Content-Range" not in response
    assert len(response.content) == 1024


def test_suffix_range(tmp_path):
    response = respond(tmp_path, HTTP_RANGE="bytes=-24")
    assert response.status_code == 206 and response["Content-Range"] == "bytes 1000-1023/1024"
    assert response.content == bytes(range(232, 256))
