# Funcionalidades do Login

Fonte: `app/web.py` (rotas `/login` e `/logout`), `app/auth/seguranca.py`,
`app/banco/usuarios.py`, `app/banco/login_tentativas.py`, `app/templates/login.html`.

## RF-01 — Autenticação por e-mail e senha

- Formulário com dois campos: e-mail (máx. 40 caracteres) e senha (máx. 40, mascarada).
- `POST /login` busca o usuário por e-mail (`buscar_usuario_por_email`) e confere a senha
  com `verificar_senha_tempo_constante`.
- Em caso de sucesso: grava na sessão `{iduser, nome, email, tipouser}` e redireciona
  para `/` (que por sua vez redireciona para o dashboard do perfil).
- Em caso de falha: mensagem **genérica** — "E-mail ou senha inválidos." — nunca diz
  qual dos dois campos está errado nem se o e-mail existe.
- `GET /login`: exibe o formulário vazio (os campos nunca vêm preenchidos, nem em caso
  de erro — o JS da página força `value = ''` no load).

## RF-02 — Hash de senha

- Senha nunca é armazenada em texto puro. `hash_senha()` usa bcrypt com salt automático
  por senha (`bcrypt.gensalt()`).
- Usado tanto no cadastro de usuário (`criar_usuario`) quanto na edição (troca de senha
  é opcional — só re-hasheia se um valor novo foi enviado).

## RF-03 — Proteção contra enumeração de e-mail (timing attack)

- `verificar_senha_tempo_constante(senha, hash_armazenado)` **sempre** roda o bcrypt,
  mesmo quando o usuário não existe — nesse caso compara contra um hash falso fixo
  (`_HASH_FALSO`) gerado uma vez na inicialização do módulo.
- Importante: a chamada não pode ficar dentro de um `if usuario and ...` com
  short-circuit, porque aí o bcrypt só rodaria quando o usuário existe, e o tempo de
  resposta voltaria a vazar quais e-mails estão cadastrados. No código atual, o bcrypt é
  chamado fora do `if`, sempre.

## RF-04 — Rate limiting / bloqueio temporário por e-mail

Tabela `login_tentativa`, controlada por `app/banco/login_tentativas.py`:

- **Limite:** 5 tentativas falhas (`LIMITE_TENTATIVAS`).
- **Janela:** 15 minutos (`JANELA_MINUTOS`) — se a última falha foi há mais tempo que
  isso, o contador reinicia em 1 em vez de incrementar.
- **Bloqueio:** ao atingir o limite dentro da janela, bloqueia por 15 minutos
  (`BLOQUEIO_MINUTOS`) a partir do momento do bloqueio.
- Antes de verificar a senha, `/login` chama `tempo_restante_bloqueio(email)`. Se
  retornar um número, a mensagem de erro passa a ser
  `"Muitas tentativas de login. Tente novamente em N minuto(s)."` e a senha nem é
  verificada.
- Login bem-sucedido limpa o registro (`registrar_login_sucesso` → `DELETE`).
- Login falho incrementa (`registrar_login_falho` → `INSERT ... ON CONFLICT DO UPDATE`,
  tudo em uma única query atômica).
- O bloqueio é **por e-mail digitado**, não por IP — então é resistente a troca de IP,
  mas não impede testar senhas em e-mails diferentes a partir do mesmo IP (isso é uma
  decisão de escopo, não uma falha: ver `03-seguranca.md`).

## RF-05 — Controle de acesso por perfil (RBAC)

- Cada usuário tem `tipouser` (no projeto original: `ADM`, `PROFESSOR`, `ALUNO`).
- Decorador `login_required`: qualquer rota que exija sessão ativa; sem sessão, redireciona para `/login`.
- Decorador `role_required(role)`: além de autenticado, exige que `tipouser` seja o
  perfil esperado; se não for, redireciona para `/` (não para um erro 403 — é um
  redirecionamento silencioso para a home do próprio usuário).
- `/` decide o dashboard de destino lendo `tipouser` da sessão.

## RF-06 — Logout

- `GET /logout` limpa toda a sessão (`session.clear()`) e redireciona para `/login`.

## RF-07 — Sessão de servidor, sem token exposto ao cliente

- Sessão é o mecanismo nativo do Flask (cookie assinado com `SECRET_KEY`), não JWT.
- Cookie de sessão configurado como:
  - `HttpOnly` — sempre ligado (JS não lê o cookie).
  - `SameSite=Lax` — sempre ligado.
  - `Secure` — ligado via env `SESSION_COOKIE_SECURE=1` (deve ser 1 em produção, atrás
    de HTTPS; em dev local sobre HTTP fica 0).

## RF-08 — CSRF

- Toda a aplicação usa `Flask-WTF` `CSRFProtect`, incluindo o formulário de login
  (`<input type="hidden" name="csrf_token" value="{{ csrf_token() }}">`).
- O token dura a sessão inteira (`WTF_CSRF_TIME_LIMIT = None`), não expira em 1h como é
  o padrão do Flask-WTF — decisão deliberada porque um usuário pode ficar mais de 1h com
  a tela de login aberta antes de submeter.

## RF-09 — Headers de segurança (aplicados a toda resposta, inclusive `/login`)

Ver detalhes e justificativa em [`03-seguranca.md`](./03-seguranca.md). Resumo:
`Cache-Control: no-store`, `X-Frame-Options: SAMEORIGIN`, `X-Content-Type-Options: nosniff`,
`Referrer-Policy: same-origin`, e `Strict-Transport-Security` quando `SESSION_COOKIE_SECURE=1`.

## RF-10 — Gestão de usuários (dependência do login, não o login em si)

Não é login propriamente, mas é a base de dados que o login consulta:

- `criar_usuario(nome, email, senha_hash, tipouser, telefone)` — cria o usuário e, se
  `tipouser` for um perfil com tabela de extensão (`PROFESSOR`/`ALUNO`), cria também o
  registro correspondente.
- `atualizar_usuario(...)` — edita dados; senha só é trocada se um valor novo for
  passado.
- `listar_usuarios()` / `listar_usuarios_por_tipo(tipo)`.
- E-mail é `UNIQUE` no banco — tentativa de duplicar gera erro tratado na camada web
  (mensagem "E-mail já cadastrado.").

## RF-11 — Usuário administrador padrão

- Script de inicialização do banco (`scripts/init_db.py`) cria um ADM padrão se não
  existir nenhum com aquele e-mail, com senha já hasheada em bcrypt. Isso garante que
  sempre há uma porta de entrada inicial no sistema recém-criado.

## Fora de escopo (não implementado)

- Recuperação de senha por e-mail ("esqueci minha senha").
- Autenticação multifator (2FA).
- Login social (Google/Facebook).
- Rate limiting por IP (só por e-mail).
- Expiração/renovação de sessão por tempo de inatividade configurável (usa o padrão do
  Flask).
- Log de auditoria de login persistido (existe uma tabela `login` no schema, com
  `idlogin`/`datahorainicial`/`datahorafinal`, mas **não é usada por nenhum código
  atual** — é um remanescente do schema, não uma funcionalidade ativa. Não recrie essa
  tabela a menos que vá implementar o log de fato).
