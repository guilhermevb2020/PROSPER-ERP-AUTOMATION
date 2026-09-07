"""Guardas do envio e idempotencia usando transporte e banco simulados."""
from contextlib import nullcontext
from types import SimpleNamespace
from unittest.mock import Mock

import pytest
from src.processors.web.boletos import enviar_lote as r


@pytest.fixture
def fluxo(monkeypatch, tmp_path):
    monkeypatch.setattr(r.sys.stdout,'reconfigure',lambda **kw:None,raising=False)
    post=Mock(return_value=SimpleNamespace(status=200,body=lambda:b'frmprintcobranca'))
    ctx=SimpleNamespace(request=SimpleNamespace(post=post))
    monkeypatch.setattr(r,'sync_playwright',lambda:nullcontext(object()))
    monkeypatch.setattr(r,'_connect_or_launch',lambda p:(ctx,None))
    monkeypatch.setattr(r,'_ler_contas',lambda c:[('1','Banco sintetico')])
    dados={'1':{'lab':'Banco sintetico','titulos':[{'id':'101','valor':10},{'id':'102','valor':20}]}}
    monkeypatch.setattr(r,'_descobrir_e_preview',lambda *a:(dados,2,30))
    for key,value in {'SCAN':False,'DRY_RUN':False,'SO_CONTA':'','MAX_CONTAS':0,'TETO':100,'PAUSA_ENTRE_CONTAS':0}.items():
        monkeypatch.setattr(r.cfg,key,value)
    for key,value in {'CONFIRMAR':True,'SO_CONTA_ID':'','SO_TIPO':'','EXIGIR_UNICO':False,'EMITIR_SE_AUSENTE':False,'SO_TITULO_IDS':set()}.items():
        monkeypatch.setattr(r,key,value)
    template=tmp_path/'envio.txt';template.write_text('x=1&Checks=old&checkEnvio=old&op1=42&op2=42&modalidadeS=C')
    monkeypatch.setattr(r.cfg,'T_ENVIO_PATH',str(template))
    monkeypatch.setattr(r._db,'get_conn',Mock(return_value=Mock()))
    monkeypatch.setattr(r,'_carregar_enviados',lambda conn:{'101'})
    registro=Mock();monkeypatch.setattr(r,'_registrar',registro)
    return ctx,registro


@pytest.mark.parametrize('guarda',['SCAN','DRY_RUN','CONFIRMAR','EXIGIR_UNICO','TETO'])
def test_guardas_impedem_envio(fluxo,monkeypatch,guarda):
    ctx,registro=fluxo
    if guarda in ('SCAN','DRY_RUN'):monkeypatch.setattr(r.cfg,guarda,True)
    elif guarda=='TETO':monkeypatch.setattr(r.cfg,'TETO',1)
    else:monkeypatch.setattr(r,guarda,guarda=='EXIGIR_UNICO')
    r.main()
    ctx.request.post.assert_not_called();registro.assert_not_called()


def test_envia_apenas_titulos_ainda_nao_enviados(fluxo):
    ctx,registro=fluxo;r.main()
    ctx.request.post.assert_called_once()
    body=ctx.request.post.call_args.kwargs['data']
    assert '102' in body and '101' not in body
    assert registro.call_args.kwargs['ids']==['102']
    assert registro.call_args.kwargs['status']=='ok'


@pytest.mark.parametrize('http,corpo,estado',[(500,b'erro','falha'),(200,b'resposta desconhecida','incerto')])
def test_resposta_sem_sucesso_nao_e_registrada_como_ok(fluxo,http,corpo,estado):
    ctx,registro=fluxo
    ctx.request.post.return_value=SimpleNamespace(status=http,body=lambda:corpo)
    r.main()
    assert registro.call_args.kwargs['status']==estado


@pytest.mark.parametrize('funcao',['_ler_contas','_titulos_conta'])
def test_sessao_expirada_nao_parece_fila_vazia(funcao):
    response=SimpleNamespace(status=200,body=lambda:b'<script>window.location="expira.php";</script>')
    page=Mock();page.evaluate.return_value=[]
    ctx=SimpleNamespace(request=SimpleNamespace(get=Mock(return_value=response),post=Mock(return_value=response)),new_page=Mock(return_value=page))
    with pytest.raises(RuntimeError,match='sessao'):
        if funcao=='_ler_contas':r._ler_contas(ctx)
        else:r._titulos_conta(ctx,'1','Banco sintetico')
