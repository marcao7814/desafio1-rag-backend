# Documentação do Módulo de Login — Sistema EAD

Esta pasta documenta o sistema de autenticação/login **do jeito que ele funciona hoje em
produção** (app Flask, `app/web.py` + `app/auth/` + `app/banco/`), para servir de
referência completa ao reescrever o mesmo login em outro projeto, com as mesmas
funcionalidades e o mesmo nível de segurança.

> Existe também uma versão antiga de login em Streamlit (`app/auth/login.py`,
> `app/main.py`). Ela é mais simples — **não tem** rate limiting, CSRF nem headers de
> segurança — e não é a usada em produção (produção roda `flask run` / gunicorn sobre
> `app/web.py`, conforme `ini.bat` e o deploy na VPS). Esta documentação descreve a
> versão Flask, que é a completa.

## Como ler esta pasta

| Arquivo | Conteúdo |
|---|---|
| [`01-funcionalidades.md`](./01-funcionalidades.md) | O que o login faz, requisito por requisito |
| [`02-banco-de-dados.md`](./02-banco-de-dados.md) | Tabelas necessárias + DDL SQL pronto para criar o banco |
| [`03-seguranca.md`](./03-seguranca.md) | Por que cada proteção existe (bcrypt, timing attack, CSRF, headers, cookies) |
| [`04-fluxos.md`](./04-fluxos.md) | Passo a passo de cada fluxo (login, bloqueio, logout, acesso por perfil) |
| [`05-guia-implementacao.md`](./05-guia-implementacao.md) | Checklist prático para reescrever isso em um projeto novo |

## Resumo rápido

- **Stack original:** Python 3 + Flask + Flask-WTF (CSRF) + PostgreSQL (psycopg2) + bcrypt.
- **Modelo de autenticação:** e-mail + senha, sessão de servidor (cookie assinado pelo Flask), sem JWT/OAuth.
- **Perfis de acesso (RBAC):** `ADM`, `PROFESSOR`, `ALUNO` — mas o núcleo do login não depende
  disso; é só uma coluna `tipouser` com `CHECK`. Em outro projeto, troque os valores do
  perfil livremente.
- **Proteções já implementadas:** hash de senha com bcrypt, verificação em tempo
  constante (não revela se o e-mail existe), rate limiting com bloqueio temporário por
  e-mail, CSRF token em todo POST, cookies de sessão `HttpOnly`/`SameSite=Lax`/`Secure`
  (configurável), headers de segurança (`X-Frame-Options`, `X-Content-Type-Options`,
  `Referrer-Policy`, HSTS opcional).
- **O que precisa existir no banco:** no mínimo as tabelas `usuario` e `login_tentativa`
  (ver [`02-banco-de-dados.md`](./02-banco-de-dados.md)). `professor`/`aluno` são
  tabelas de extensão específicas do domínio EAD — em outro projeto, troque por suas
  próprias tabelas de perfil, seguindo o mesmo padrão.
