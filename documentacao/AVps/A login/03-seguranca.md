# Segurança do Login — Por que cada decisão existe

Cada item aqui tem uma causa concreta (não é "boa prática" genérica solta) — útil para
não simplificar demais ao reescrever em outro projeto.

## 1. Hash de senha com bcrypt (salt automático)

- `bcrypt.gensalt()` gera um salt novo por senha, embutido no próprio hash resultante.
  Duas senhas iguais geram hashes diferentes — impede ataques de rainbow table e
  identificar visualmente senhas repetidas entre contas.
- `bcrypt.checkpw()` extrai o salt do hash armazenado automaticamente; não precisa
  guardar salt em coluna separada.

## 2. Verificação em tempo constante (anti-enumeração de e-mail)

**Problema que isso resolve:** se o código fizesse
`if usuario and verificar_senha(senha, usuario["senha"])`, o `and` faz short-circuit —
quando o e-mail não existe, `verificar_senha` nunca é chamada, e a resposta volta quase
instantaneamente. Quando o e-mail existe, o bcrypt roda (propositalmente lento, ~100ms+)
antes de responder. Um atacante consegue distinguir "e-mail não existe" de "e-mail
existe, senha errada" só medindo o tempo de resposta — mesmo que a mensagem de erro seja
idêntica nos dois casos.

**Solução implementada:** `verificar_senha_tempo_constante` sempre chama
`bcrypt.checkpw`, trocando o hash real por um hash falso fixo (`_HASH_FALSO`, gerado uma
vez quando o módulo carrega) quando o usuário não existe. E, na rota `/login`, essa
chamada é feita **fora** de qualquer `and` com short-circuit — sempre roda,
independente de o usuário existir.

```python
senha_hash = usuario["senha"] if usuario else None
senha_confere = verificar_senha_tempo_constante(senha, senha_hash)  # sempre roda bcrypt
if usuario and senha_confere:
    ...
```

Ao reescrever, o erro mais fácil de cometer é "simplificar" essa lógica de volta para
`if usuario and verificar_senha(...)` — isso reabre a brecha de timing silenciosamente.

## 3. Mensagem de erro genérica

"E-mail ou senha inválidos." sempre — nunca "e-mail não encontrado" nem "senha
incorreta". Informar qual dos dois está errado permite enumerar e-mails cadastrados sem
nem precisar medir tempo de resposta.

## 4. Rate limiting por e-mail (não por IP)

- Decisão de escopo: bloquear por e-mail impede o ataque mais comum contra login
  (tentar várias senhas no e-mail de uma vítima específica — credential stuffing contra
  uma conta), sem exigir rastrear IP (que pode ser falsificado/rotativo, e em alguns
  ambientes corporativos muitos usuários legítimos compartilham IP via NAT, o que
  tornaria bloqueio por IP um risco de bloquear gente inocente).
- Isso **não** protege contra um atacante testando e-mails diferentes em sequência
  (enumeração de contas) — se precisar disso em outro projeto, some um rate limit
  adicional por IP ou por sessão/dispositivo na camada de borda (proxy/CDN/WAF), não no
  código da aplicação.
- A query de incremento (`registrar_login_falho`) é uma única instrução
  `INSERT ... ON CONFLICT DO UPDATE` com toda a lógica condicional dentro do SQL —
  evita uma condição de corrida "ler contador, calcular, escrever" em requisições
  concorrentes para o mesmo e-mail (duas abas tentando logar ao mesmo tempo, por
  exemplo).

## 5. CSRF (Cross-Site Request Forgery)

- `Flask-WTF` `CSRFProtect` ativado globalmente — qualquer `POST` sem token válido é
  rejeitado automaticamente pelo framework, incluindo `/login`.
- Sem isso, um site malicioso poderia montar um formulário escondido que submete
  `POST /login` (ou qualquer outra rota que mude estado) usando a sessão do usuário sem
  ele saber.
- `WTF_CSRF_TIME_LIMIT = None`: o padrão do Flask-WTF expira o token em 1 hora. Como a
  tela de login pode ficar aberta por mais tempo que isso antes do usuário digitar a
  senha, o token foi configurado para durar a sessão inteira em vez de expirar sozinho.

## 6. Cookie de sessão

| Flag | Valor | Por quê |
|---|---|---|
| `HttpOnly` | sempre ligado | JavaScript não consegue ler o cookie — mitiga roubo de sessão via XSS |
| `SameSite` | `Lax` | cookie não é enviado em requisições cross-site de terceiros (CSRF adicional, além do token) |
| `Secure` | ligado via `SESSION_COOKIE_SECURE=1` em produção | cookie só é enviado por HTTPS — nunca ligar isso sem o site já estar 100% atrás de TLS, senão o cookie simplesmente nunca seria enviado e o login pareceria quebrado |

## 7. Headers de segurança (aplicados a toda resposta via `after_request`)

| Header | Valor | Mitiga |
|---|---|---|
| `Cache-Control` | `no-store, no-cache, must-revalidate, max-age=0` | páginas autenticadas (inclusive a própria tela pós-login) ficarem em cache do navegador/proxy e serem recuperadas por outra pessoa no mesmo computador |
| `X-Frame-Options` | `SAMEORIGIN` | clickjacking (embutir o site num `<iframe>` de outro domínio) — `SAMEORIGIN`, não `DENY`, porque a própria aplicação usa iframe interno para exibir PDF/vídeo/HTML de materiais |
| `X-Content-Type-Options` | `nosniff` | o navegador tentar "adivinhar" o tipo de um arquivo e executá-lo como script |
| `Referrer-Policy` | `same-origin` | vazar a URL completa (que pode conter dados sensíveis na querystring) para domínios externos via header `Referer` |
| `Strict-Transport-Security` | só quando `SESSION_COOKIE_SECURE=1` | força HTTPS em visitas futuras — só habilitar depois que o HTTPS já está garantido, senão pode travar acesso em ambientes sem certificado válido |

## 8. Conteúdo enviado por usuário (upload), relacionado indiretamente ao login

Fora do escopo direto do login, mas na mesma camada de segurança: arquivos `.html`
enviados por um perfil (ex.: professor) e servidos de volta ganham
`Content-Security-Policy: sandbox allow-scripts` — garante que HTML/JS arbitrário de
terceiros nunca rode com os cookies/sessão da aplicação, mesmo se alguém abrir a URL do
arquivo direto numa aba. Vale considerar o mesmo padrão em qualquer projeto novo que
aceite upload de HTML/SVG.

## 9. O que **não** foi implementado e deve ser decisão explícita no novo projeto

- 2FA / MFA.
- Rotação/expiração de senha.
- Política de complexidade de senha (não há validação de força de senha no cadastro).
- Rate limit por IP.
- Lista de senhas vazadas (ex.: HaveIBeenPwned API) no cadastro.
- Revogação de sessão ativa remotamente ("sair de todos os dispositivos").

Essas ausências são aceitáveis para o escopo original (sistema EAD interno, poucos
usuários), mas devem ser avaliadas conscientemente, não copiadas por omissão, se o novo
projeto tiver uma superfície de ataque maior (ex.: cadastro público aberto à internet).
