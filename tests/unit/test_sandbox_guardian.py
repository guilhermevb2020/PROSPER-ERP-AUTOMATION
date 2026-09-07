import os
from pathlib import Path
from types import SimpleNamespace
import pytest
from scripts.sandbox import _ambiente as a


@pytest.fixture(autouse=True)
def ambiente_isolado(monkeypatch):
    monkeypatch.setattr(os,"environ",dict(os.environ))


def config(tmp_path, monkeypatch, cap="__GUARDIAN_SANDBOX_CAPSOLVER_API_KEY__"):
    path=tmp_path/"sandbox.env"
    path.write_text("SANDBOX_EMAIL=sandbox@example.invalid\nSANDBOX_SENHA=GSMARTPWD3\n"
        +"SANDBOX_CAPSOLVER_API_KEY="+cap+"\nSANDBOX_GRAVAR=false\n"
        +"SANDBOX_PERFIL="+str(tmp_path/"perfil")+"\n"
        +"SANDBOX_EVIDENCIA_DIR="+str(tmp_path/"evidencia")+"\n")
    monkeypatch.setattr(a,"ENV_SANDBOX",str(path))


def test_identidade_sandbox_nao_herda_producao(tmp_path,monkeypatch):
    config(tmp_path,monkeypatch)
    monkeypatch.setattr(a,"_guardian",lambda cfg:{})
    monkeypatch.setenv("BOLETO_EMAIL","producao@example.invalid")
    monkeypatch.setenv("BOLETO_SENHA","GSMARTPWD1")
    monkeypatch.setenv("CAPSOLVER_API_KEY","__GUARDIAN_CAPSOLVER_API_KEY__")
    a.carregar_env(log=lambda s:None)
    assert os.environ["BOLETO_EMAIL"]=="sandbox@example.invalid"
    assert os.environ["BOLETO_SENHA"]=="GSMARTPWD3"
    assert os.environ["CAPSOLVER_API_KEY"]=="__GUARDIAN_SANDBOX_CAPSOLVER_API_KEY__"


def test_alias_smart_com_chave_errada_e_recusado(tmp_path,monkeypatch):
    config(tmp_path,monkeypatch,cap="__GUARDIAN_CAPSOLVER_API_KEY__")
    with pytest.raises(a.SandboxSemCredencial,match="sua chave"):
        a.carregar_env(log=lambda s:None)


def test_host_sem_ca_nao_faz_fallback_direto(tmp_path,monkeypatch):
    monkeypatch.setattr(a,"RAIZ",tmp_path/"docker/automation/erp")
    with pytest.raises(a.SandboxSemCredencial,match="CA do Guardian ausente"):
        a._guardian({"SANDBOX_GUARDIAN_PROXY":"http://127.0.0.1:3128"})


def test_chrome_usa_proxy_e_nss_privado(monkeypatch):
    monkeypatch.setenv("SANDBOX_GUARDIAN_PROXY","http://127.0.0.1:3128")
    monkeypatch.setenv("SANDBOX_GUARDIAN_BROWSER_HOME","/private/browser-home")
    seen={}
    def launch(**kwargs):seen.update(kwargs);return "context"
    p=SimpleNamespace(chromium=SimpleNamespace(launch_persistent_context=launch))
    assert a.abrir_chrome(p,"/private/profile")=="context"
    assert seen["proxy"]=={"server":"http://127.0.0.1:3128","bypass":"localhost,127.0.0.1"}
    assert seen["env"]["HOME"]=="/private/browser-home"
    assert not seen.get("ignore_https_errors",False)
    assert not any("ignore-certificate-errors" in x for x in seen["args"])


def test_trace_recusa_credencial_literal_antes_de_criar_perfil(tmp_path,monkeypatch):
    config(tmp_path,monkeypatch)
    p=tmp_path/"sandbox.env"
    p.write_text(p.read_text().replace("GSMARTPWD3","legacy-example").replace("SANDBOX_GRAVAR=false","SANDBOX_GRAVAR=true"))
    with pytest.raises(a.SandboxSemCredencial,match="Trace exige apelidos"):
        a.carregar_env(log=lambda s:None)
    assert not (tmp_path/"perfil").exists()
