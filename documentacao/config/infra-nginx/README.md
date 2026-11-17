# infra-nginx — Proxy reverso compartilhado da VPS

Nginx único na VPS Hostinger que ocupa sozinho as portas 80/443 e roteia por
subdomínio para cada projeto hospedado (este `projeto-ead` e os que vierem
depois). Cada projeto, por sua vez, **não publica mais porta nenhuma** — só
expõe a porta interna e entra na rede externa `proxy_net` para o nginx
alcançá-lo pelo nome do container.

Fica fora do repositório de qualquer projeto específico porque é
infraestrutura da VPS como um todo, não de um projeto só. Na VPS, vive em algo
como `/opt/infra-nginx/` — separado de `/opt/ead/`, `/opt/outro-projeto/`, etc.

## Deploy inicial (uma vez só por VPS)

```bash
docker network create proxy_net

cd /opt/infra-nginx   # copie esta pasta (documentos/config/infra-nginx) para cá
docker compose up -d nginx
```

## Adicionar um novo projeto

1. No `docker-compose.yml` do projeto, garanta que o serviço web:
   - não publica porta (`expose`, não `ports`);
   - tem `container_name` fixo e único (ex. `outro-projeto-web`);
   - entra também na rede externa `proxy_net` (`networks: [default, proxy_net]`).
2. Crie `conf.d/outro-projeto.conf` aqui, copiando o modelo de
   [`conf.d/projeto-ead.conf`](./conf.d/projeto-ead.conf), trocando o domínio
   e o `proxy_pass` para o `container_name` do novo projeto.
3. Recarregue o nginx compartilhado:
   ```bash
   docker compose exec nginx nginx -s reload
   ```

## Emitir certificado HTTPS (Certbot, método webroot)

O nginx aqui roda em container, então o plugin `--nginx` do Certbot (que edita
e reinicia um nginx do sistema operacional) não se aplica. Em vez disso,
usamos o método `--webroot`: o Certbot só precisa conseguir escrever um
arquivo em `/var/www/certbot` e que o nginx sirva esse caminho por HTTP — o
bloco `location /.well-known/acme-challenge/` já configurado em cada
`conf.d/*.conf` cuida disso.

```bash
docker compose run --rm certbot certonly \
  --webroot -w /var/www/certbot \
  -d SEU-IP-COM-HIFEN.sslip.io \
  --email SEU-EMAIL --agree-tos --no-eff-email
```

Depois:
1. Descomente o bloco `server { listen 443 ssl; ... }` no `conf.d/<projeto>.conf` correspondente.
2. `docker compose exec nginx nginx -s reload`.
3. No `.env` do projeto, ligue `SESSION_COOKIE_SECURE=1` e reinicie o `web` dele.

## Renovação automática

Os certificados do Let's Encrypt expiram a cada 90 dias. Adicione um cron na
VPS (fora do Docker) para renovar e recarregar o nginx periodicamente:

```bash
# crontab -e
0 3 * * * cd /opt/infra-nginx && docker compose run --rm certbot renew --quiet && docker compose exec nginx nginx -s reload
```
