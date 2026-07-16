# Развёртывание МЭТР на рег.облаке (Ubuntu)

Пошагово: от чистого сервера до работающей панели с HTTPS.
Всё поднимается в Docker: `PostgreSQL + веб-панель + воркер + Caddy` (авто-HTTPS).

Обозначения: `SERVER_IP` — IP вашего сервера, `USER` — ваш пользователь на сервере
(например `root` или созданный вами), `metr.example.ru` — ваш домен (если есть).

---

## 0. Что нужно заранее

- Сервер на рег.облаке с Ubuntu, вы знаете `SERVER_IP` и пароль/ключ для входа.
- В **панели рег.облака** (firewall / сетевые правила) открыты порты
  **22 (SSH), 80 (HTTP), 443 (HTTPS)**.
- Желательно домен (для HTTPS). Без домена можно временно по IP (без шифрования).

---

## 1. Подключиться к серверу по SSH

На вашем Windows-компьютере откройте **PowerShell** и выполните:

```powershell
ssh USER@SERVER_IP
```

(Введите пароль. OpenSSH встроен в Windows 10/11.)

---

## 2. Установить Docker

На сервере:

```bash
sudo apt update && sudo apt upgrade -y
curl -fsSL https://get.docker.com | sudo sh
sudo usermod -aG docker $USER
```

Выйдите и зайдите снова, чтобы права группы применились:

```bash
exit
```
```powershell
ssh USER@SERVER_IP
```

Проверка:

```bash
docker --version && docker compose version
```

---

## 3. Настроить firewall на сервере

```bash
sudo ufw allow OpenSSH
sudo ufw allow 80
sudo ufw allow 443
sudo ufw --force enable
```

---

## 4. Перенести проект на сервер

Вариант А — **scp** (проще). На вашем Windows (новое окно PowerShell, НЕ внутри ssh):

```powershell
scp -r "C:\Users\yaros\OneDrive\Desktop\restoran AI\restopulse" USER@SERVER_IP:~/
```

Папка окажется на сервере как `~/restopulse`.

Вариант Б — git (удобно для будущих обновлений): залейте проект в приватный
репозиторий GitHub/GitLab и `git clone` на сервере.

---

## 5. Настроить .env

На сервере:

```bash
cd ~/restopulse
cp .env.example .env
nano .env
```

Обязательно задайте:

| Переменная | Что вписать |
|---|---|
| `ADMIN_PASSWORD` | пароль входа в панель (придумайте надёжный) |
| `SECRET_KEY` | длинная случайная строка — сгенерируйте: `openssl rand -hex 32` |
| `POSTGRES_PASSWORD` | пароль БД (любой надёжный) |
| `METR_SITE_ADDRESS` | ваш домен `metr.example.ru` **или** `:80` (если пока без домена) |

Токены ассистентов и соцсетей (`TELEGRAM_*`, `VK_*` и т.д.) можно оставить пустыми
и заполнить позже прямо в панели (`/settings`). Сохраните файл: `Ctrl+O`, `Enter`, `Ctrl+X`.

Быстро сгенерировать секрет:

```bash
openssl rand -hex 32
```

---

## 6. Запустить

```bash
docker compose up -d --build
docker compose ps          # все сервисы должны быть Up
docker compose logs -f web # логи панели (Ctrl+C чтобы выйти из просмотра)
```

Первый сборка образа занимает пару минут.

- Если `METR_SITE_ADDRESS=:80` → откройте `http://SERVER_IP` — увидите вход в панель.
- Если задан домен → см. следующий шаг (HTTPS включится сам).

---

## 7. Домен и HTTPS

1. У регистратора домена (или в DNS рег.ру) создайте **A-запись**:
   `metr.example.ru → SERVER_IP`. Подождите, пока запись распространится (обычно минуты).
2. В `.env` укажите `METR_SITE_ADDRESS=metr.example.ru` и перезапустите:

   ```bash
   docker compose up -d
   ```
3. Caddy автоматически получит сертификат Let's Encrypt. Через минуту откройте
   `https://metr.example.ru` — замок в браузере, вход по `ADMIN_PASSWORD`.

> Для выпуска сертификата обязательно должны быть открыты порты 80 и 443, а домен
> уже указывать на сервер.

---

## 8. Первый вход

Откройте адрес панели → введите `ADMIN_PASSWORD`. Дальше:

- `/settings` — подключите AI-ассистента (YandexGPT/GigaChat/…) и соцсети (VK/Telegram);
- `/content` — генерация, модерация и публикация постов;
- `/` — мгновенный анализ конкурентов.

---

## Авто-деплой (GitHub Actions)

Настраивается один раз. После этого любой `git push` в `main` сам выкатывается
на сервер: **тесты → сборка → проверка здоровья → автооткат, если не поднялось.**
Вручную заходить на сервер больше не нужно.

Схема намеренно устроена так, что ключ от сервера лежит **только** в секретах
GitHub — ни у кого на руках его быть не обязано.

### 1. Создать ключ деплоя (на своём компьютере)

```powershell
ssh-keygen -t ed25519 -C "github-deploy-metr" -f $env:USERPROFILE\.ssh\metr_deploy -N '""'
```

Появятся два файла: `metr_deploy` (приватный) и `metr_deploy.pub` (публичный).

### 2. Разрешить этому ключу вход на сервер

```powershell
type $env:USERPROFILE\.ssh\metr_deploy.pub | ssh USER@SERVER_IP "mkdir -p ~/.ssh && chmod 700 ~/.ssh && cat >> ~/.ssh/authorized_keys && chmod 600 ~/.ssh/authorized_keys"
```

Проверка (должно ответить `ok`, не спрашивая пароль):

```powershell
ssh -i $env:USERPROFILE\.ssh\metr_deploy USER@SERVER_IP "echo ok"
```

### 3. Положить секреты в GitHub

Репозиторий → **Settings → Secrets and variables → Actions → New repository secret**.
Три секрета:

| Имя | Значение |
|---|---|
| `DEPLOY_HOST` | IP или домен сервера, например `194.67.111.11` |
| `DEPLOY_USER` | пользователь SSH, например `root` |
| `DEPLOY_SSH_KEY` | **приватный** ключ целиком — содержимое `metr_deploy` |

Приватный ключ скопировать вместе со строками `-----BEGIN…` и `-----END…`:

```powershell
type $env:USERPROFILE\.ssh\metr_deploy | clip
```

### 4. Проверить

Вкладка **Actions** → workflow «Тесты и деплой» → **Run workflow**.
Дальше выкатка идёт сама на каждый push в `main`.

### Что защищает прод

- **Тесты — шлагбаум**: красные тесты → выкатки не будет вовсе.
- **Проверка здоровья**: после сборки ждём `/health` до 90 секунд.
- **Автооткат**: не поднялось — сервер сам возвращается на прошлую версию,
  прод не остаётся лежать. В логе Actions будут последние строки логов `web`.
- **Очередь**: две выкатки одновременно не столкнутся (`concurrency`).
- Пока секреты не заданы, шаг выкатки просто пропускается — сборка зелёная.

`.env` на сервере не трогается: он не в git, а `git reset --hard` не удаляет
неотслеживаемые файлы.

### Откатиться вручную

```bash
cd ~/metr
git log --oneline -5          # найти нужную версию
git reset --hard <хеш>
docker compose up -d --build
```

---

## Обслуживание

**Обновить версию** (после переноса новых файлов через scp или `git pull`):

```bash
cd ~/restopulse
docker compose up -d --build
```

**Логи:**

```bash
docker compose logs -f web
docker compose logs -f worker
```

**Проверка здоровья:**

```bash
curl -s http://localhost/health
# {"status":"ok","storage":"postgres"}
```

**Резервная копия БД:**

```bash
docker compose exec -T db pg_dump -U metr metr > ~/metr_backup_$(date +%F).sql
```

**Остановить / запустить:**

```bash
docker compose down     # остановить (данные в томе сохраняются)
docker compose up -d    # запустить снова
```

---

## Безопасность (кратко)

- Панель за паролем (`ADMIN_PASSWORD`) — не оставляйте пустым на сервере.
- Порт приложения (8000) наружу не открыт — только через Caddy (80/443).
- Все ключи и токены хранятся в БД на вашем сервере в РФ (152-ФЗ), наружу не отдаются.
- Держите сервер обновлённым: `sudo apt update && sudo apt upgrade -y`.
