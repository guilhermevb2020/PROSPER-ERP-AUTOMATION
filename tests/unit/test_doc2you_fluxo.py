"""Download, colisao de nomes, falhas e paginacao sem conexoes externas."""
from types import SimpleNamespace
from unittest.mock import AsyncMock, Mock

import pytest

from src.processors.web.doc2you import baixar_dia as r
from src.processors.web.doc2you import download as d


@pytest.mark.asyncio
@pytest.mark.parametrize('status', [201, 204, 500])
async def test_upload_so_conta_sucesso_confirmado(monkeypatch, status):
    monkeypatch.setattr(r.D, 'baixar_documento', AsyncMock(return_value=b'%PDF'+b'x'*2048))
    monkeypatch.setattr(r.D, 'resolver_cnpj', Mock(return_value='00000000000000'))
    monkeypatch.setattr(r.C, 'nome_final', Mock(return_value='documento'))
    upload = Mock(return_value=status)
    monkeypatch.setattr(r.NC, 'enviar', upload)
    res = {'enviados':0, 'erros':0}; ops=set()
    await r._processar_docs(object(), [{'chk':'1','tipo':'teste','operacao':'42'}],
                           'operacao','2026-09-07',res,ops,set())
    assert res == {'enviados': int(status in (201,204)), 'erros': int(status == 500)}
    assert bool(ops) == (status in (201,204))


@pytest.mark.asyncio
async def test_colisao_de_nomes_preserva_ambos_documentos(monkeypatch):
    monkeypatch.setattr(r.D,'baixar_documento',AsyncMock(return_value=b'%PDF'+b'x'*2048))
    monkeypatch.setattr(r.D,'resolver_cnpj',Mock(return_value=''))
    monkeypatch.setattr(r.C,'nome_final',Mock(return_value='mesmo_nome'))
    upload=Mock(return_value=201);monkeypatch.setattr(r.NC,'enviar',upload)
    docs=[{'chk':str(i),'tipo':'teste','operacao':'42'} for i in (1,2)]
    res={'enviados':0,'erros':0}
    await r._processar_docs(object(),docs,'operacao','2026-09-07',res,set(),set())
    nomes=[c.args[2] for c in upload.call_args_list]
    assert nomes == ['mesmo_nome.pdf','mesmo_nome_2.pdf']
    assert res == {'enviados':2,'erros':0}


@pytest.mark.asyncio
async def test_download_invalido_nao_e_enviado(monkeypatch):
    monkeypatch.setattr(r.D,'baixar_documento',AsyncMock(return_value=b''))
    upload=Mock();monkeypatch.setattr(r.NC,'enviar',upload)
    res={'enviados':0,'erros':0}
    await r._processar_docs(object(),[{'chk':'1','tipo':'teste'}],'operacao','2026-09-07',res,set(),set())
    upload.assert_not_called();assert res['erros']==1


@pytest.mark.asyncio
async def test_paginacao_para_quando_servidor_repete_documentos(monkeypatch):
    docs=[{'chk':'1','status':'C'},{'chk':'2','status':'C'}]
    monkeypatch.setattr(d.C,'parse_listagem',Mock(return_value=docs))
    post=AsyncMock(return_value=SimpleNamespace(text=AsyncMock(return_value='pagina simulada')))
    ctx=SimpleNamespace(request=SimpleNamespace(post=post))
    result=await d.listar_documentos(ctx,'2026-09-04','2026-09-07')
    assert result==docs and post.await_count==2
    assert [x.kwargs['form']['page'] for x in post.call_args_list]==['1','2']
