from types import SimpleNamespace
from src.processors.web.boletos import _sessao as sessao

class Elemento:
    def __init__(self, value='', visible=True):
        self.value=value;self.visible=visible;self.clicks=0
    def is_visible(self):return self.visible
    def input_value(self):return self.value
    def click(self, **kwargs):self.clicks+=1

class Lista:
    def __init__(self,items):self.items=items
    def count(self):return len(self.items)
    def nth(self,i):return self.items[i]
    @property
    def first(self):return self
    def is_visible(self):return bool(self.items) and self.items[0].is_visible()
    def click(self,**kwargs):self.items[0].click(**kwargs)

def pagina(email, *, visible=True, url='https://www.smartsecurities.com.br/smart/loginsec.php'):
    campo=Elemento(email,visible);botao=Elemento()
    def locator(selector):
        return Lista([campo] if selector=='input[type="text"][disabled]' else [botao])
    return SimpleNamespace(frames=[SimpleNamespace(url=url,locator=locator)]),botao

def test_retoma_somente_identidade_esperada():
    page,button=pagina('Financeiro@example.invalid')
    assert sessao._retomar_usuario_reconhecido(page,'financeiro@example.invalid')
    assert button.clicks==1

def test_nao_retoma_outra_identidade():
    page,button=pagina('outra@example.invalid')
    assert not sessao._retomar_usuario_reconhecido(page,'financeiro@example.invalid')
    assert button.clicks==0

def test_nao_retoma_campo_oculto():
    page,button=pagina('financeiro@example.invalid',visible=False)
    assert not sessao._retomar_usuario_reconhecido(page,'financeiro@example.invalid')
    assert button.clicks==0

def test_nao_clica_em_outro_frame():
    page,button=pagina('financeiro@example.invalid',url='https://www.google.com/recaptcha/')
    assert not sessao._retomar_usuario_reconhecido(page,'financeiro@example.invalid')
    assert button.clicks==0


def test_identifica_expiracao_explicita_do_smart():
    pg=SimpleNamespace(url='https://www.smartsecurities.com.br/',title=lambda:'Sessão Expirada')
    assert sessao._retomada_expirada(SimpleNamespace(pages=[pg]))

def test_nao_invalida_pagina_sem_expiracao():
    pg=SimpleNamespace(url='https://www.smartsecurities.com.br/',title=lambda:'SmartSecurities')
    assert not sessao._retomada_expirada(SimpleNamespace(pages=[pg]))
