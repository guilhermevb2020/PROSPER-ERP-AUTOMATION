# 🔄 Status da Conversão Selenium → Nodriver

## ✅ CONCLUÍDO (60% do código)

### Infraestrutura
- ✅ [nodriver_utils.py](src/common/nodriver_utils.py) - Módulo completo
- ✅ [requirements.txt](requirements.txt) - nodriver>=0.33 adicionado
- ✅ Imports atualizados no processador
- ✅ `__init__()` - browser/tab/display configurado

### Métodos Convertidos para Async
1. ✅ `iniciar_navegador()` - Linha 135
2. ✅ `aguardar_extensao_resolver_captcha_login()` - Linha 191 (**SIMPLIFICADO** de 160 linhas para 75 linhas!)
3. ✅ `clicar_botao_acessar_login()` - Linha 267

---

## ⏳ PENDENTE (40% do código)

### Métodos que PRECISAM ser convertidos:

**CRÍTICOS (necessários para funcionar):**
1. ❌ `fazer_login_automatico()` - Linha 311
   - Usar `await self.tab.find()` e `await human_type()`
   - Remover lógica de `switch_to.frame()` (Nodriver acessa automaticamente)

2. ❌ `navegar_para_titulos_abertos()` - Linha 460
   - `execute_script()` → `await self.tab.evaluate()`

3. ❌ `mudar_para_frame_code()` - Linha 483
   - **IMPORTANTE**: Nodriver NÃO tem `switch_to.frame()` !
   - Frames são transparentes, elementos são encontrados automaticamente
   - Pode ser que esse método inteiro seja **DESNECESSÁRIO**

4. ❌ `preencher_datas()` - Linha 259
   - Converter busca e JS para async

5. ❌ `marcar_checkbox_recomendacao()` - Linha 334
   - Simples conversão para async

6. ❌ `clicar_pesquisar()` - Linha 373
   - Simples conversão

7. ❌ `selecionar_todos_resultados()` - Linha 426
   - Simples conversão

8. ❌ `verificar_e_resolver_recaptcha()` - Linha 477
   - Usar lógica simplificada (mesmo de `aguardar_extensao_resolver_captcha_login()`)

9. ❌ `clicar_gerar_csv()` - Linha 1109
   - Simples conversão

10. ❌ `executar_extracao_completa()` - Linha 1154
    - Adicionar `await` em todas as chamadas

11. ❌ `processar()` - Linha 1213 (**MÉTODO PRINCIPAL**)
    - Converter para async
    - Adicionar `await` em `iniciar_navegador()` e `fazer_login_automatico()`

**DELETAR (não são mais necessários):**
- ❌ `resolver_recaptcha_com_capsolver()` - Linha 707
- ❌ `resolver_captcha_imagens_com_capsolver()` - Linha 718

---

## 📝 PADRÃO DE CONVERSÃO RÁPIDA

### Buscar elemento:
```python
# ANTES (Selenium)
elemento = self.driver.find_element(By.ID, "foo")

# DEPOIS (Nodriver)
elemento = await self.tab.find("#foo")  # ou wait_for_element(self.tab, "#foo")
```

### Clicar:
```python
# ANTES
elemento.click()

# DEPOIS
await elemento.click()  # ou await human_click(elemento)
```

### Digitar:
```python
# ANTES
elemento.send_keys("texto")

# DEPOIS
await elemento.send_keys("texto")  # ou await human_type(elemento, "texto")
```

### Executar JS:
```python
# ANTES
self.driver.execute_script("document.title")

# DEPOIS
await self.tab.evaluate("document.title")
```

### Sleep:
```python
# ANTES
time.sleep(2)

# DEPOIS
await asyncio.sleep(2)
```

---

## 🚨 PROBLEMA: Frames no Nodriver

**Selenium tem:**
```python
self.driver.switch_to.frame("code")
self.driver.switch_to.frame("text")
```

**Nodriver NÃO TEM `switch_to`!**

**Solução:** Nodriver encontra elementos em iframes automaticamente:
```python
# Elemento está em iframe? Nodriver encontra sozinho!
elemento = await self.tab.find("#elemento_no_iframe")
```

**CONSEQUÊNCIA:**
- `mudar_para_frame_code()` pode virar um **no-op** (não fazer nada)
- OU ser deletado completamente
- Testes dirão se precisa de lógica especial

---

## 🎯 PRÓXIMOS PASSOS

**Opção 1 (Rápida):** Eu converto TUDO agora em batch (15-20min)
- Converto os 11 métodos restantes de uma vez
- Deleto funções obsoletas
- Ajusto `__main__` para `asyncio.run()`

**Opção 2 (Cautelosa):** Converter método por método
- Você aprova cada mudança antes da próxima
- Mais lento mas mais controle

**Opção 3 (Intermediária):** Converter por grupo
- Grupo 1: Login (fazer_login, navegação)
- Grupo 2: Preenchimento (datas, checkboxes, pesquisa)
- Grupo 3: Processamento (extração, CSV, loop principal)

---

## ⚡ RECOMENDAÇÃO

**Opção 1** - Deixa eu converter tudo agora porque:
1. Padrão é repetitivo (90% é busca/clique/digita)
2. Já temos `nodriver_utils.py` pronto
3. Lógica de CAPTCHA já foi simplificada
4. Frames são transparentes no Nodriver (menos código!)
5. Posso testar depois de tudo convertido

**Você quer que eu continue com conversão em batch (Opção 1)?**
