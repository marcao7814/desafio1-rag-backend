# Testes de Segurança — Tela de Login (Produção)

> Testes feitos direto em `https://2-25-71-176.sslip.io/login`, em produção, em 2026-11-16. Metodologia: requisições HTTP reais via `curl` (sessão + CSRF token válidos extraídos da página), sem ferramentas automatizadas de pentest. Escopo: autenticação e cabeçalhos HTTP da aplicação — não cobre infraestrutura de rede/SO da VPS.

## Resultado

3 problemas reais encontrados e **corrigidos** no mesmo ciclo; 1 observado e já adequado; 1 mitigação adicional de baixo risco aplicada por precaução.

| # | Teste | Resultado | Severidade |
|---|---|---|---|
| 1 | Enumeração de usuário por tempo de resposta (timing attack) | 🔴 Vulnerável → corrigido | Média |
| 2 | Força bruta / tentativas ilimitadas de senha | 🔴 Vulnerável → corrigido | Alta |
| 3 | Clickjacking (ausência de `X-Frame-Options`) | 🔴 Vulnerável → corrigido | Média |
| 4 | SQL Injection (campo e-mail) | ✅ Já protegido (queries parametrizadas) | — |
| 5 | CSRF no formulário de login | ✅ Já protegido (Flask-WTF) | — |
| 6 | Cookie de sessão (`Secure`/`HttpOnly`/`SameSite`) | ✅ Já correto | — |
| 7 | Mensagem de erro revela se e-mail existe | ✅ Já genérica ("E-mail ou senha inválidos") | — |
| 8 | Versão do nginx exposta no header `Server` | 🟡 Informativo → mitigado | Baixa |

---

## 1. Enumeração de usuário por tempo de resposta

**Teste:** medi o tempo de resposta do `POST /login` para um e-mail existente (com senha errada) contra um e-mail inexistente, repetindo 3x cada.

**Resultado (antes da correção):**
```
e-mail existente (admin@gmail.com) + senha errada: ~0.70–0.76s
e-mail inexistente:                                 ~0.47–0.50s
```

**Por quê:** o código só roda `bcrypt.checkpw()` (operação deliberadamente lenta, ~250ms) quando o e-mail é encontrado no banco. Se o e-mail não existe, a resposta volta na hora — mesmo a mensagem de erro sendo idêntica nos dois casos ("E-mail ou senha inválidos"), o **tempo** de resposta já entrega se aquele e-mail está cadastrado ou não. Um atacante consegue descobrir e-mails válidos (ex. de professores/alunos) só cronometrando tentativas de login, sem precisar acertar a senha.

**Correção:** `app/auth/seguranca.py` ganhou `verificar_senha_tempo_constante()`, que sempre roda o `bcrypt.checkpw()` — contra um hash falso pré-computado quando o e-mail não existe — para o tempo de resposta ser o mesmo nos dois casos. `app/web.py` foi ajustado para chamar essa função **fora** de um `and` com a variável `usuario` (o `and` faria *short-circuit* e puraria o bcrypt de novo quando o e-mail não existe, reabrindo a mesma brecha).

**Resultado (depois da correção, teste local):** os dois casos passaram a ficar na mesma faixa de tempo (sobrepostos entre ~0.4–1.6s, sem diferença sistemática entre existente/inexistente).

---

## 2. Força bruta / tentativas ilimitadas

**Teste:** 8 tentativas de login seguidas com a mesma conta (`admin@gmail.com`) e senhas erradas diferentes.

**Resultado (antes da correção):**
```
tentativa 1 → HTTP 200 (erro genérico)
tentativa 2 → HTTP 200
...
tentativa 8 → HTTP 200
```
Nenhuma tentativa foi bloqueada, atrasada ou sinalizada. Não existia CAPTCHA, limite de taxa (*rate limit*) nem bloqueio temporário — um atacante pode tentar senhas indefinidamente contra qualquer conta, inclusive a do ADM.

**Correção:** nova tabela `login_tentativa` (`scripts/init_db.py`) e módulo `app/banco/login_tentativas.py`:
- cada falha de login incrementa um contador por e-mail;
- ao atingir **5 falhas em 15 minutos**, a conta fica bloqueada por **15 minutos** (`Muitas tentativas de login. Tente novamente em N minuto(s).`);
- login correto reseta o contador;
- a lógica roda inteira no Postgres (não em memória do processo Python) — funciona corretamente mesmo com múltiplos workers do Gunicorn, que não compartilham memória entre si.

**Resultado (depois da correção, teste local):** tentativas 1–5 retornam o erro normal; a partir da 6ª, a mensagem de bloqueio aparece. Login correto com até 4 falhas anteriores continua funcionando normalmente e zera o contador.

---

## 3. Clickjacking

**Teste:** verifiquei os cabeçalhos de resposta de `/login` em busca de `X-Frame-Options` e `Content-Security-Policy: frame-ancestors`.

**Resultado (antes da correção):** nenhum dos dois presente — a página podia ser carregada dentro de um `<iframe>` em **qualquer site externo**, abrindo caminho para um ataque clássico de clickjacking (ex. um site malicioso sobrepõe elementos invisíveis sobre o login real para induzir cliques/ações do usuário autenticado sem ele perceber).

**Correção:** `X-Frame-Options: SAMEORIGIN` adicionado no `after_request` global (`app/web.py`) — bloqueia qualquer tentativa de embutir a aplicação em outro domínio, mas **sem** quebrar o uso legítimo que a própria aplicação já faz de `<iframe>` (visualização de PDF/vídeo/HTML das aulas a partir de `/uploads/...`, que é same-origin). Usei `SAMEORIGIN` em vez de `DENY` justamente por causa desse uso interno — `DENY` teria quebrado os visualizadores de material das aulas.

Também adicionei `X-Content-Type-Options: nosniff` e `Referrer-Policy: same-origin` no mesmo header global, e `Strict-Transport-Security` (HSTS) condicionado a `SESSION_COOKIE_SECURE=1` (já ativo em produção).

---

## 4. SQL Injection

**Teste:** enviei `admin@gmail.com' OR '1'='1` no campo e-mail do login.

**Resultado:** erro genérico normal ("E-mail ou senha inválidos"), sem bypass nem erro de banco exposto. O código usa `psycopg2` com queries parametrizadas (`%s`) em todo lugar — não há concatenação de SQL com entrada do usuário. **Nenhuma ação necessária.**

---

## 5–7. CSRF, cookies de sessão, mensagem de erro genérica

Já cobertos por código existente e confirmados nos testes:
- **CSRF:** `Flask-WTF` (`CSRFProtect`) exige token válido em todo POST; requisição sem token retorna 400.
- **Cookie de sessão:** `Set-Cookie: session=...; Secure; HttpOnly; Path=/; SameSite=Lax` — confirmado no header real da resposta de login.
- **Mensagem de erro:** idêntica para e-mail inexistente e senha errada (a vulnerabilidade real nesse ponto era o *tempo* de resposta, não o texto — ver item 1).

Nenhuma ação necessária nesses três.

---

## 8. Versão do nginx exposta

**Teste:** `Server: nginx/1.31.8` presente no header de toda resposta.

**Por quê importa (pouco):** não é explorável por si só, mas facilita um atacante automatizar a busca por CVEs específicos daquela versão exata do nginx, em vez de ter que adivinhar.

**Correção:** `server_tokens off;` adicionado ao vhost em `documentos/config/infra-nginx/conf.d/projeto-ead.conf` (nos dois blocos, HTTP e o modelo HTTPS comentado) — o header passa a mostrar só `nginx`, sem o número da versão.

---

## O que NÃO foi testado neste ciclo (fora do escopo)

- Varredura de portas / serviços na VPS (SSH, firewall) — já coberto em `documentos/config/config.md`.
- Testes de carga / DoS (não executados propositalmente — poderiam derrubar a produção).
- Fuzzing automatizado ou scanner de vulnerabilidades (ex. OWASP ZAP, Burp) — este ciclo foi manual, focado na tela de login.
- Segurança do upload de aulas (PDF/vídeo/HTML) — já tratada em commit anterior (sandbox do iframe de HTML, validação de extensão, IDOR no download).

## Arquivos alterados nesta correção

- `app/auth/seguranca.py` — `verificar_senha_tempo_constante()`
- `app/banco/login_tentativas.py` (novo) — controle de tentativas/bloqueio
- `app/web.py` — rota `/login` corrigida, headers de segurança globais
- `scripts/init_db.py` — tabela `login_tentativa`
- `documentos/config/infra-nginx/conf.d/projeto-ead.conf` — `server_tokens off`
