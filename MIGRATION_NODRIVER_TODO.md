# 🔄 Migração Selenium → Nodriver - CHECKLIST

## ✅ CONCLUÍDO

1. **Módulo nodriver_utils.py criado** - [src/common/nodriver_utils.py](src/common/nodriver_utils.py)
   - Funções async para iniciar browser, esperar elementos, cliques humanos, etc.

2. **requirements.txt atualizado**
   - Adicionado: `nodriver>=0.33`

3. **Imports atualizados** - [src/processors/web/titulos_abertos_e_marcados_recompras.py](src/processors/web/titulos_abertos_e_marcados_recompras.py:1-33)
   - Removido: `selenium`, `By`, `ActionChains`
   - Adicionado: `nodriver`, `asyncio`, `Browser`, `Tab`

4. **`__init__()` atualizado**
   - Adicionado: `self.browser`, `self.tab`, `self.display`
   - Removido: `self.driver` (substituído por `self.tab`)

5. **`iniciar_navegador()` convertido para async**
   - Usa `init_browser()` do `nodriver_utils.py`
   - Configura display virtual (Xvfb)

---

## ⏳ PENDENTE - Converter para Async

Todos os métodos abaixo precisam virar `async def` e substituir:
- `self.driver` → `self.tab`
- `time.sleep()` → `await asyncio.sleep()`
- `find_element()` → `await self.tab.find()`
- `.click()` → `await element.click()`
- `.send_keys()` → `await element.send_keys()`
- `.execute_script()` → `await self.tab.evaluate()`

### Métodos a converter (em ordem de prioridade):

1. **✅ `aguardar_extensao_resolver_captcha_login()` - SIMPLIFICAR**
   - Remover lógica de iframes complexa
   - Nova lógica simples:
     ```python
     async def aguardar_extensao_resolver_captcha_login(self):
         # 1. Aguardar token aparecer (max 60s)
         for i in range(60):
             token = await self.tab.evaluate("document.getElementById('g-recaptcha-response')?.value || ''")
             if token:
                 print(f"[CAPTCHA] ✅ Resolvido em {i+1}s!")
                 return True
             await asyncio.sleep(1)

         # 2. Timeout → pausar para manual
         self.pausado = True
         print("[CAPTCHA] ⚠️ Timeout, pausando para resolução manual")

         while self.pausado and not self.parar:
             await asyncio.sleep(0.5)

         return not self.parar
     ```

2. **`clicar_botao_acessar_login()` → async**
   - Simples, só converter `find_element` → `await self.tab.find()`

3. **`fazer_login_automatico()` → async**
   - Converter para async
   - Usar `await wait_for_element()` e `await human_type()`

4. **`navegar_para_titulos_abertos()` → async**
   - `execute_script()` → `await self.tab.evaluate()`

5. **`mudar_para_frame_code()` → async**
   - **IMPORTANTE**: Nodriver trata frames diferente
   - Frames são acessados automaticamente, sem `switch_to.frame()`
   - Pode precisar buscar elementos diretamente pelo seletor CSS

6. **`preencher_datas()` → async**
   - Converter busca e preenchimento

7. **`marcar_checkbox_recomendacao()` → async**
   - Simples conversão

8. **`clicar_pesquisar()` → async**
   - Simples conversão

9. **`selecionar_todos_resultados()` → async**
   - Simples conversão

10. **`verificar_e_resolver_recaptcha()` → async + SIMPLIFICAR**
    - Mesma lógica simplificada do `aguardar_extensao_resolver_captcha_login()`

11. **`renomear_csv_baixado()` → MANTER SYNC**
    - Operações de arquivo não precisam ser async

12. **`clicar_gerar_csv()` → async**
    - Simples conversão

13. **`executar_extracao_completa()` → async**
    - Adicionar `await` em todas as chamadas

14. **`processar()` → async**
    - Método principal vira async
    - `__main__` precisa chamar `asyncio.run(processar())`

15. **DELETAR métodos obsoletos:**
    - `resolver_recaptcha_com_capsolver()` (linha 913)
    - `resolver_captcha_imagens_com_capsolver()` (linha 924)
    - Não são mais necessários (extensão resolve tudo)

---

## 📝 NOTAS IMPORTANTES

### Frames no Nodriver
Nodriver **NÃO** tem `switch_to.frame()`. Frames são transparentes:
- Buscar elemento diretamente: `await tab.find("#elemento_no_iframe")`
- Nodriver encontra automaticamente elementos em iframes aninhados

### `self.driver` vs `self.tab`
- Selenium: `self.driver` (navegador + aba atual)
- Nodriver: `self.browser` (navegador) + `self.tab` (aba ativa)
- Maioria das operações usa `self.tab`

### Padrão de Conversão

**ANTES (Selenium sync):**
```python
def meu_metodo(self):
    elemento = self.driver.find_element(By.ID, "foo")
    elemento.click()
    time.sleep(2)
```

**DEPOIS (Nodriver async):**
```python
async def meu_metodo(self):
    elemento = await self.tab.find("foo")  # ID inferido automaticamente
    await elemento.click()
    await asyncio.sleep(2)
```

### Executar Script JS

**ANTES:**
```python
self.driver.execute_script("return document.title")
```

**DEPOIS:**
```python
await self.tab.evaluate("document.title")
```

---

## 🚀 PRÓXIMOS PASSOS

1. Converter `fazer_login_automatico()` para async (mais crítico)
2. Simplificar toda lógica de CAPTCHA (remover 90% do código)
3. Converter métodos de navegação e preenchimento
4. Converter `processar()` para async
5. Testar localmente
6. Configurar Xvfb/VNC na VM
7. Testar em produção

---

## 🧪 COMO TESTAR

```bash
# 1. Instalar dependências
pip install -r requirements.txt

# 2. Configurar display (se necessário)
export DISPLAY=:1

# 3. Rodar processador
python -m src.processors.web.titulos_abertos_e_marcados_recompras
```

---

## ❓ DÚVIDAS?

- Nodriver docs: https://github.com/ultrafunkamsterdam/nodriver
- Frames: Nodriver acessa automaticamente, sem `switch_to`
- CAPTCHA: Extensão resolve automaticamente após 1 clique
- Display: `:1` = Xvfb/VNC na VM

