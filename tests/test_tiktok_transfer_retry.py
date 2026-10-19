from types import SimpleNamespace

import httpx

import app.publishing as publishing


class FakeResponse:
    def __init__(self,status_code:int):
        self.status_code=status_code
        self.headers={}
    def raise_for_status(self):
        if self.status_code >= 400:
            request=httpx.Request("PUT","https://upload.example.invalid/chunk")
            response=httpx.Response(self.status_code,request=request)
            raise httpx.HTTPStatusError(f"HTTP {self.status_code}",request=request,response=response)


class SequenceClient:
    def __init__(self,sequence):
        self.sequence=list(sequence)
        self.calls=0
    def put(self,*args,**kwargs):
        value=self.sequence[self.calls]
        self.calls+=1
        if isinstance(value,BaseException):
            raise value
        return FakeResponse(int(value))


def _settings():
    return SimpleNamespace(publish_max_attempts=4)


def test_tiktok_chunk_retries_429_then_succeeds(monkeypatch):
    monkeypatch.setattr(publishing,"load_settings",_settings)
    monkeypatch.setattr(publishing.time,"sleep",lambda _:None)
    client=SequenceClient([429,200])
    publishing._tiktok_put_chunk(client,"https://upload.example.invalid/chunk","video/mp4",b"abc",0,3)
    assert client.calls==2


def test_tiktok_chunk_retries_transport_timeout_then_succeeds(monkeypatch):
    monkeypatch.setattr(publishing,"load_settings",_settings)
    monkeypatch.setattr(publishing.time,"sleep",lambda _:None)
    request=httpx.Request("PUT","https://upload.example.invalid/chunk")
    client=SequenceClient([httpx.ReadTimeout("socket stalled",request=request),200])
    publishing._tiktok_put_chunk(client,"https://upload.example.invalid/chunk","video/mp4",b"abc",0,3)
    assert client.calls==2


def test_tiktok_chunk_does_not_retry_permanent_4xx(monkeypatch):
    monkeypatch.setattr(publishing,"load_settings",_settings)
    monkeypatch.setattr(publishing.time,"sleep",lambda _:None)
    client=SequenceClient([400,200])
    try:
        publishing._tiktok_put_chunk(client,"https://upload.example.invalid/chunk","video/mp4",b"abc",0,3)
        assert False,"400 must fail"
    except httpx.HTTPStatusError as exc:
        assert exc.response.status_code==400
    assert client.calls==1
