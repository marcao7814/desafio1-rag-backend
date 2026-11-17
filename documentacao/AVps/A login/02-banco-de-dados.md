# Banco de Dados — O que criar para o login funcionar

PostgreSQL 13+. Fonte: `scripts/init_db.py` (DDL real usada em produção).

## 1. Tabelas essenciais do login (sempre necessárias)

### `usuario`

Tabela central de autenticação. Em outro projeto, é a única tabela **obrigatória** para
o login básico funcionar.

```sql
CREATE TABLE IF NOT EXISTS usuario (
    iduser      SERIAL PRIMARY KEY,
    nome        VARCHAR(100) NOT NULL,
    email       VARCHAR(100) UNIQUE NOT NULL,
    senha       VARCHAR(200) NOT NULL,   -- hash bcrypt, nunca texto puro
    tipouser    VARCHAR(20) NOT NULL CHECK (tipouser IN ('ADM', 'PROFESSOR', 'ALUNO')),
    telefone    VARCHAR(20)
);
```

> Troque a lista do `CHECK (tipouser IN (...))` pelos perfis do novo projeto (ex.:
> `'ADMIN', 'CLIENTE', 'OPERADOR'`). `VARCHAR(200)` para `senha` é de propósito maior que
> o hash bcrypt (60 chars) — dá margem para trocar de algoritmo de hash no futuro sem
> migrar a coluna.

### `login_tentativa`

Obrigatória para ter rate limiting / bloqueio por tentativas falhas.

```sql
CREATE TABLE IF NOT EXISTS login_tentativa (
    email            VARCHAR(100) PRIMARY KEY,
    tentativas       INTEGER NOT NULL DEFAULT 0,
    ultima_tentativa TIMESTAMP NOT NULL DEFAULT NOW(),
    bloqueado_ate    TIMESTAMP
);
```

- `email` é a PK (não FK para `usuario.email`) de propósito: o rate limiting precisa
  registrar tentativas mesmo para e-mails que **não existem** em `usuario` (alguém
  tentando adivinhar um e-mail cadastrado). Se fosse FK, a tentativa de um e-mail
  inexistente falharia silenciosamente ou exigiria tratamento extra.
- `bloqueado_ate NULL` = não bloqueado. A lógica de leitura/escrita está em
  `04-fluxos.md` e no código de referência do guia de implementação.

## 2. Tabelas de extensão de perfil (específicas do domínio EAD — adapte ao seu projeto)

O padrão aqui é: `usuario` guarda só o que é universal (credenciais + tipo). Cada perfil
que precisa de dados extras tem sua própria tabela 1:1 com `usuario`, criada **apenas**
quando um usuário daquele tipo é cadastrado.

```sql
CREATE TABLE IF NOT EXISTS professor (
    idprofessor SERIAL PRIMARY KEY,
    iduser      INTEGER NOT NULL REFERENCES usuario(iduser) ON DELETE CASCADE
);

CREATE TABLE IF NOT EXISTS aluno (
    idaluno     SERIAL PRIMARY KEY,
    iduser      INTEGER NOT NULL REFERENCES usuario(iduser) ON DELETE CASCADE
);
```

Em outro projeto, isso se torna, por exemplo, `cliente (idcliente, iduser)` e
`operador (idoperador, iduser)` — ou pode nem existir, se todos os perfis usam só os
campos de `usuario`. **Não é parte do núcleo do login**, é só o padrão de extensão.

## 3. Tabela de auditoria (existe no schema, mas não é usada — opcional)

```sql
CREATE TABLE IF NOT EXISTS login (
    idlogin          SERIAL PRIMARY KEY,
    iduser           INTEGER NOT NULL REFERENCES usuario(iduser) ON DELETE CASCADE,
    datahorainicial  TIMESTAMP NOT NULL DEFAULT NOW(),
    datahorafinal    TIMESTAMP,
    tipouser         VARCHAR(20)
);
```

Só crie essa tabela se for implementar o registro de sessões de fato (nenhum código
atual grava ou lê nela — ver nota em `01-funcionalidades.md`).

## 4. Índices

- `usuario.email` já tem índice implícito por ser `UNIQUE`.
- `login_tentativa.email` já é `PRIMARY KEY` — leitura por e-mail é O(1) de índice.
- Nenhum índice adicional é necessário para o volume de um módulo de login.

## 5. Dados iniciais (seed)

Para o sistema ter uma porta de entrada logo após criar o banco:

```sql
-- Senha abaixo é só exemplo — gere o hash com bcrypt.hashpw() em código,
-- nunca insira a senha em texto puro.
INSERT INTO usuario (nome, email, senha, tipouser)
SELECT 'Administrador', 'admin@exemplo.com', '<hash_bcrypt_aqui>', 'ADM'
WHERE NOT EXISTS (SELECT 1 FROM usuario WHERE email = 'admin@exemplo.com');
```

No projeto original isso é feito em Python (`scripts/init_db.py`), gerando o hash com
`hash_senha()` antes do `INSERT` — replicar assim é mais seguro do que gerar hash em SQL.

## 6. Variáveis de ambiente de conexão

| Variável | Papel | Padrão (se ausente) |
|---|---|---|
| `DB_HOST` | host do PostgreSQL | `localhost` |
| `DB_PORT` | porta | `5432` |
| `DB_NAME` | nome do banco | — |
| `DB_USER` | usuário | — |
| `DB_PASSWORD` | senha | — (sem padrão, obrigatório) |
| `SECRET_KEY` | assina cookie de sessão/CSRF do Flask | — (gerar forte, nunca hardcode) |
| `SESSION_COOKIE_SECURE` | `1` em produção (HTTPS), `0` em dev local | `0` |

Essas variáveis nunca vão para o repositório — só para `.env` (fora do controle de
versão) e para o ambiente real de produção.

## 7. Idempotência do script de criação

O script original cria o schema com `CREATE TABLE IF NOT EXISTS` e aplica migrações
pontuais com blocos `DO $$ ... EXCEPTION WHEN duplicate_column THEN NULL; END $$;` para
colunas novas em tabelas já existentes — permite rodar o script de inicialização
repetidas vezes em produção sem erro (útil em deploy). Replique esse padrão se o novo
projeto também fizer deploy via script de migração simples (sem uma ferramenta de
migração dedicada como Alembic/Flyway).
