# Фінальний проєкт: «Колекція цитат» в AWS

**Курс:** GoIT Cloud Computing  
**Дата:** 4 листопада 2026 року  
**Регіон:** `us-east-1` (N. Virginia)  
**Середовище:** AWS Elastic Beanstalk, `quotes-env`  
**Застосунок:** <http://quotes-env.eba-9dpvcp9d.us-east-1.elasticbeanstalk.com>  
**API:** <http://quotes-env.eba-9dpvcp9d.us-east-1.elasticbeanstalk.com/docs>  
**Health check:** <http://quotes-env.eba-9dpvcp9d.us-east-1.elasticbeanstalk.com/health>

Звіт відповідає плану фінального завдання GoIT. Стан AWS підтверджено збереженими скриншотами; доступність URL під час перевірки залежить від того, чи залишено навчальний стенд увімкненим. Для перегляду вкладених зображень потрібно зберегти структуру каталогів `docs/` та `img/`.

## 1. Архітектура рішення та вибір технологій

### Призначення застосунку

«Колекція цитат» — вебзастосунок з українським інтерфейсом для створення, перегляду, редагування та видалення цитат. Реалізовано пошук за текстом і автором, фільтр за категорією, випадкову цитату й посторінкове завантаження. Дані зберігаються у спільній PostgreSQL незалежно від життєвого циклу EC2.

### Стек і обґрунтування

| Компонент | Вибір та обґрунтування |
|---|---|
| Середовище | **Elastic Beanstalk** встановлює залежності, запускає Python-процес і керує EC2, ALB та Auto Scaling без адміністрування Kubernetes |
| Backend | **Python 3.13, FastAPI, Uvicorn**: HTTP API, валідація даних, автоматична API-документація |
| Робота з БД | **SQLAlchemy 2, psycopg 3**: транзакції, повторне використання підключень і PostgreSQL |
| Frontend | **HTML/CSS/JavaScript**: український інтерфейс без окремої процедури збирання |
| Сховище | **RDS PostgreSQL**: реляційні дані та спільна БД для всіх реплік |
| Мережа | **VPC, public/private subnets, IGW, NAT**: відокремлення зовнішнього трафіку від застосунку й БД |
| Балансування | **Application Load Balancer**: HTTP-маршрутизація та перевірка `/health` |
| Безпека | **IAM roles, Security Groups, Secrets Manager**: обмеження мережевого доступу та пароль поза кодом |
| Спостереження | **CloudWatch Metrics, Logs, Alarms, SNS**: метрики, журнали та email |
| Витрати | **AWS Budgets, Cost Explorer**: пороги сповіщень та аналіз нарахувань |

В AWS використано Python-платформу Beanstalk. Docker Compose у репозиторії призначений для локального запуску; ECR, ECS та EKS у цьому розгортанні не використовуються.

### Графічна схема

![Архітектура застосунку в AWS](../img/00-architecture.png)

Окремі файли: [PNG](../img/00-architecture.png) · [SVG для друку та масштабування](../img/00-architecture.svg).

Шлях запиту: **браузер → ALB:80 → nginx на приватному EC2:80 → Uvicorn/FastAPI:8000 → RDS:5432**. Для PostgreSQL у рядку підключення задано `sslmode=require`. NAT забезпечує вихідні з’єднання приватних ресурсів і не входить до маршруту вхідного запиту браузера. Beanstalk отримує секрет за роллю EC2 та передає застосунку змінну `DATABASE_URL`.

ALB працює у двох зонах. EC2 можуть запускатися в обох приватних підмережах, але мінімум групи — один екземпляр. RDS — **Single-AZ**, NAT Gateway — **один для обох зон**. Отже, схема не означає повної відмовостійкості всіх компонентів.

## 2. Розгортання інфраструктури в AWS

Ресурси створено через AWS Console. Призначення власної групи ALB додатково застосовано через AWS CLI у CloudShell.

### 2.1. VPC і маршрути

VPC **`quotes-vpc`**, ID `vpc-0106dd90b1f31ad0b`, CIDR **`10.20.0.0/16`**.

| Підмережа | Зона | CIDR | Призначення |
|---|---|---|---|
| public1 | us-east-1a | 10.20.0.0/20 | Публічна частина мережі, ALB |
| public2 | us-east-1b | 10.20.16.0/20 | Публічна частина мережі, ALB |
| private1 | us-east-1a | 10.20.128.0/20 | EC2 та DB subnet group |
| private2 | us-east-1b | 10.20.144.0/20 | EC2 та DB subnet group |

У public subnets маршрут `0.0.0.0/0` спрямовано до Internet Gateway. В обох private subnets цей маршрут спрямовано до NAT Gateway. EC2 не отримують public IPv4. Для S3 створено gateway endpoint.

![Карта VPC](../img/08-vpc-map.png)

![Маршрути публічних підмереж](../img/09-quotes-vpc-rtb-public.png)

Прив’язки public subnets: [09-vpc-routes-public-b.png](../img/09-vpc-routes-public-b.png).

![Маршрути private1](../img/10-vpc-routes-private.png)

Друга приватна таблиця: [10-vpc-routes-private-b.png](../img/10-vpc-routes-private-b.png).

### 2.2. Security Groups

| Група | ID | Вхідний доступ |
|---|---|---|
| quotes-alb-sg | sg-07ddb5ddd574b1c26 | TCP 80 з 0.0.0.0/0 |
| quotes-app-sg | sg-0cc04036a1566951d | TCP 80 лише від quotes-alb-sg |
| quotes-db-sg | sg-0da33dd4bbc789f7f | TCP 5432 лише від quotes-app-sg |

Клієнт звертається до ALB. Порт Uvicorn 8000 не відкрито для інтернету, PostgreSQL не має public access. На EC2 також присутня службова група Beanstalk; перевірений сукупний вхідний доступ — HTTP від групи ALB.

![Правила групи застосунку](../img/12-sg-app.png)

![Правила групи бази даних](../img/13-sg-db.png)

Додаткові підтвердження: [правило ALB](../img/11-sg-alb.png), [група на ALB](../img/17-alb-security.png), [сукупні правила EC2](../img/12-ec2-security.png).

### 2.3. IAM та секрети

Service role **`quotes-eb-service-role`** має політики `AWSElasticBeanstalkEnhancedHealth` і `AWSElasticBeanstalkManagedUpdatesCustomerRolePolicy`.

EC2 instance profile **`quotes-eb-ec2-role`** має `AWSElasticBeanstalkWebTier` та inline policy `quotes-read-database-url`, яка дозволяє `secretsmanager:GetSecretValue` для конкретного ARN секрету проєкту.

Секрет **`quotes/database-url`** містить рядок підключення до RDS. У конфігурації `DATABASE_URL` вибрано джерело **Secrets Manager** і посилання на ARN. Пароль і значення секрету у звіті не розкриваються.

![Призначені ролі та посилання на секрет](../img/14-iam-profile.png)

![Політики EC2-ролі](../img/14-iam-profile-b.png)

### 2.4. База даних

| Параметр | Значення |
|---|---|
| DB instance | quotes-db |
| Engine | PostgreSQL 18.3 |
| Class | db.t4g.micro |
| Deployment | Single-AZ |
| Початкове сховище | 20 GiB, gp2 |
| Database name | quotes |
| DB subnet group | quotes-db-subnets, дві приватні підмережі |
| Publicly accessible | **No** |
| Security Group / port | quotes-db-sg / 5432 |
| Шифрування сховища | Увімкнено, AWS managed key aws/rds |

Таблиця `quotes` містить `id`, `text`, `author`, `category`, `created_at`. SQLAlchemy повторно використовує підключення через пул; `pool_pre_ping=True` перевіряє їх перед використанням. Сесія закривається після запиту, engine звільняється при завершенні процесу. RDS Proxy не створювався.

![RDS Available, приватні підмережі та Publicly accessible No](../img/15-rds-connectivity.png)

![DB subnet group](../img/15-rds-subnets.png)

## 3. Деплой вебзастосунку

### 3.1. Фактичне середовище

| Параметр | Значення |
|---|---|
| Application / Environment | quote-collection / quotes-env |
| Environment ID | e-b5jmakrabd |
| Platform | Python 3.13 running on 64-bit Amazon Linux 2023 |
| Platform version | 4.14.0 |
| Перевірена версія застосунку | quotes-v3 |
| Tier / type | Web server / Load balanced |
| EC2 | t3.micro, x86_64, On-Demand |
| Proxy / deployment policy | nginx / All at once |

![Успішне розгортання середовища](../img/01-beanstalk-overview.png)

Версію `quotes-v3` і Health: Ok також видно на [скриншоті конфігурації](../img/14-iam-profile.png).

### 3.2. Інструкція відтворення

1. Створити VPC, чотири підмережі, маршрути IGW/NAT та Security Groups за розділом 2.
2. Створити DB subnet group тільки з двох приватних підмереж. Створити окрему RDS PostgreSQL з базою `quotes`, без public access, з групою `quotes-db-sg`.
3. Зберегти SQLAlchemy URL у секреті `quotes/database-url`. Формат: `postgresql+psycopg://USER:PASSWORD@RDS_ENDPOINT:5432/quotes?sslmode=require`. Використати власні реквізити; спеціальні символи в логіні та паролі закодувати для URL.
4. Створити service role та EC2 instance profile; надати EC2 доступ до конкретного секрету.
5. Зібрати ZIP із вмісту зовнішнього каталогу `app/`. У корені ZIP мають бути `Procfile`, `requirements.txt`, `.ebextensions/` та внутрішній Python-пакет `app/`. Не включати `.env`, локальну БД, паролі й кеші.
6. Створити Beanstalk application `quote-collection`, environment `quotes-env`, Standard / Web server / Load balanced. Вибрати Python 3.13 AL2023 і завантажити ZIP як Local file.
7. Вибрати VPC проєкту, private subnets для EC2, public IP вимкнути. Для публічного ALB вибрати дві public subnets. Призначити IAM-ролі й групи безпеки.
8. Додати `DATABASE_URL`: Source — Secrets Manager, Value — повний ARN секрету. Для процесу ALB задати HTTP:80, `/health`, success code 200.
9. Увімкнути Enhanced health, CloudWatch instance logs зі зберіганням 7 днів; задати Auto Scaling min 1 / max 2 та параметри розділу 4.
10. Дочекатися Health: Ok; відкрити Domain, перевірити `/health`, CRUD і повторний деплой з новою version label.

Команда запуску [Procfile](../app/Procfile):

```text
web: uvicorn app.main:create_app --factory --host 0.0.0.0 --port 8000
```

Ініціалізація БД у [.ebextensions/01_init_db.config](../app/.ebextensions/01_init_db.config):

```yaml
container_commands:
  01_init_db:
    command: "/var/app/venv/*/bin/python -m app.init_db"
    leader_only: true
```

`leader_only` запускає команду на одному екземплярі під час деплою. Ініціалізатор створює таблицю та завантажує `seed.csv` лише в порожню таблицю. Поточний CSV містить **50 цитат**. Повторна ініціалізація непорожньої таблиці не дублює записи й не перезаписує зміни. CSV перевіряється до запису та завантажується транзакційно. Для майбутніх змін схеми потрібні міграції.

Локальний запуск і збирання ZIP: [кореневий README](../README.md).

### 3.3. Підтвердження роботи

![Український інтерфейс і збережені цитати](../img/02-app-quotes-3.png)

![Редагування та фільтрація](../img/03-app-edi-2.png)

![Видалення цитати](../img/05-app-delete.png)

![Успішна відповідь health](../img/06-app-health.png)

![Дані збережені після повторного деплою](../img/07-app-persistence.png)

Версія після повторного розгортання: [07-app-persistence-b.png](../img/07-app-persistence-b.png). Дані зберігаються в RDS, тому повторний деплой не створює нове локальне сховище.

## 4. Моніторинг, логування та масштабування

### 4.1. ALB та health check

ALB **`awseb--AWSEB-GnxSBQzjnqYT`** — Internet-facing, дві public subnets. Listener HTTP:80 спрямовує запити до target group **`awseb-AWSEB-0YZAYQFP61BB`**, EC2:80.

| Health check | Значення |
|---|---|
| Path / success code | /health / 200 |
| Interval / timeout | 15 с / 5 с |
| Healthy / unhealthy threshold | 3 / 5 |

`/health` виконує запит до таблиці `quotes`, отже перевіряє також доступність БД. За помилки SQLAlchemy застосунок повертає HTTP 503 без розкриття реквізитів.

![ALB та listener](../img/17-alb-listener.png)

![Health check](../img/18-alb-targets-b.png)

### 4.2. CloudWatch

Dashboard **`quotes-dashboard`** містить шість віджетів:

| Віджет | Метрика / статистика |
|---|---|
| EC2 CPU (%) | CPUUtilization / Average |
| ALB Requests | RequestCount / Sum |
| ALB Response Time (s) | TargetResponseTime / Average |
| ALB Healthy Targets | HealthyHostCount / Minimum |
| RDS Connections | DatabaseConnections / Average |
| Application 5xx Errors | HTTPCode_Target_5XX_Count / Sum |

Базовий моніторинг EC2 — **5 хвилин**. Для healthy targets використовувався також період 1 хвилина метрик ALB. CPU-віджет прив’язаний до початкового EC2; рішення Auto Scaling приймаються за метрикою групи, а не за цим окремим віджетом.

Для 5xx видно **No data available**: відсутність точок не є виміряним значенням 0. Відсутність помилок конкретного навантажувального сценарію окремо підтверджує лічильник скрипту.

![Dashboard CloudWatch](../img/20-cloudwatch-dashboard.png)

Повну історію навантаження та переходів healthy targets 1 → 2 → 1 наведено також у розділі 6. Instance log streaming увімкнено, строк зберігання логів — **7 днів**.

![Журнали застосунку](../img/19-cloudwatch-logs.png)

### 4.3. CloudWatch alarm і SNS

| Параметр | Значення |
|---|---|
| Alarm | quotes-unhealthy-targets |
| Namespace / metric | AWS/ApplicationELB / UnHealthyHostCount |
| Dimensions | ALB та target group застосунку |
| Statistic / period | Maximum / 1 хвилина |
| Умова | >= 1, два порушення з двох періодів |
| Missing data | Not breaching |
| Дія | SNS topic quotes-alerts |

Email-підписку підтверджено, тестове повідомлення отримано. Це підтверджує доставлення SNS; примусове спрацювання саме цього alarm та відповідний alarm-лист збереженими матеріалами не підтверджено.

![CloudWatch alarm](../img/21-cloudwatch-alarm.png)

![Дія alarm через SNS](../img/21-cloudwatch-alarm-b.png)

![Підтверджена підписка](../img/22-sns-subscription.png)

![Отриманий тестовий email SNS](../img/23-sns-message.png)

### 4.4. Auto Scaling

| Параметр | Фактичне значення демонстрації |
|---|---|
| Min / Max | 1 / 2 EC2 |
| Fleet | On-Demand |
| Metric / Statistic / Unit | CPUUtilization / Average / Percent |
| Period / Breach duration | 5 хв / 5 хв |
| Upper / Lower threshold | 5% / 2% |
| Scale up / Scale down increment | +1 / −1 |
| Cooldown | 360 с |

Пороги 5% / 2% вибрано для демонстрації автоматичних переходів під доступним тестовим навантаженням. Це навчальні значення, а не обґрунтовані пороги промислової системи.

![Фактичні параметри Auto Scaling](../img/24-scaling-settings.png)

## 5. Оптимізація та контроль витрат

### 5.1. AWS Budgets

Місячний Cost budget **`fp-budget`** — **10 USD**. Email-пороги: **Actual 85%, Actual 100%, Forecast 100%**; адресата підтверджено. На скриншоті поточні витрати бюджету — 2,51 USD, прогноз — 24,65 USD. Перевищення прогнозу є сигналом обмежити тривалість роботи стенда.

Бюджет надсилає сповіщення; автоматичного вимкнення ресурсів не налаштовано.

![Бюджет](../img/31-budget.png)

![Пороги бюджету](../img/31-budget-b.png)

### 5.2. Cost Explorer

Збережений звіт: діапазон **2026-11-03 — 2026-11-05**, **Daily**, групування **Service**. Поточний підсумок — **0,40 USD**. Найбільші показані статті: Elastic Load Balancing — 0,20 USD, EC2-Instances — 0,09 USD, VPC — 0,09 USD. Значення округлені.

Charge type виключає **Credit та Refund**; показаний підсумок не є сумою до оплати після кредитів. Окремого фільтра ресурсів проєкту немає: це дані облікового запису за вибраним діапазоном. День роботи стенда ще не повністю відображено, тому 0,40 USD не є фінальною вартістю проєкту. У Budgets інший період і параметри, тож показники не повинні безпосередньо збігатися.

![Витрати за сервісами та параметри звіту](../img/32-cost-explorer.png)

### 5.3. Реалізовані обмеження

- **Максимум 2 EC2**, мінімум 1; після зниження навантаження додатковий екземпляр видаляється автоматично.
- `t3.micro` для застосунку, `db.t4g.micro` для БД.
- Базовий моніторинг EC2 — 5 хвилин; retention instance logs — 7 днів.
- Один NAT та RDS Single-AZ зменшують кількість постійно працюючих компонентів порівняно з NAT у кожній зоні й резервною БД, але знижують відмовостійкість.
- RDS Proxy, X-Ray та ALB access logs не ввімкнено. ALB, NAT, RDS та сховище залишаються джерелами витрат навіть без запитів.

![Строк зберігання логів і 5-хвилинний моніторинг](../img/33-cost-controls-b.png)

Обмеження max instances 2 видно на [24-scaling-settings.png](../img/24-scaling-settings.png); дублюючий кадр не потрібний. Після захисту заплановано видалення навчальних ресурсів за [планом очищення з розділу 7](#7-план-очищення-та-видалення-ресурсів). Під час підготовки звіту ресурси не видалялися.

## 6. Тестування та перевірка роботи системи

### 6.1. Функціональні перевірки

| Перевірка | Підтвердження |
|---|---|
| Публічний URL та український інтерфейс | 02-app-quotes-3.png |
| Створення, редагування, пошук і категорії | 02-app-quotes-3.png, 03-app-edi-2.png |
| Видалення | 05-app-delete.png |
| Доступність застосунку та БД | 06-app-health.png: {"status":"ok"} |
| Persistence після повторного деплою | 07-app-persistence.png, 07-app-persistence-b.png |
| Готовність обох цілей після scale-out | 28-scaling-targets.png |
| Доставка тестового повідомлення | 23-sns-message.png |

У репозиторії дев’ять автоматизованих тестів: три HTTP-сценарії та шість сценаріїв CSV. Перевіряються CRUD, persistence, пошук, фільтри, випадкова цитата, пагінація, валідація, seed та відсутність часткового імпорту. Локальні тести використовують SQLite; роботу PostgreSQL в AWS підтверджують застосунок, `/health` та скриншоти RDS.

Команда локального запуску тестів із каталогу `app/`:

```powershell
python -m unittest discover -s tests -v
```

### 6.2. Навантажувальне тестування

[Скрипт app/load_test.py](../app/load_test.py) виконує read-only GET-запити до `/api/quotes?limit=20`, не змінюючи записи. Команда з кореня репозиторію:

```powershell
python app/load_test.py --url http://quotes-env.eba-9dpvcp9d.us-east-1.elasticbeanstalk.com --duration 900 --workers 10
```

| Показник | Фактичний результат |
|---|---|
| Початок | 2026-11-04 14:05:34 UTC+01:00 / 13:05:34 UTC |
| Час на останньому рядку | 900,2 с |
| Потоки | 10 |
| Successful | **35 075** |
| Errors | **0** |
| Обчислена середня інтенсивність | Близько **39 запитів/с**: 35 075 / 900,2 |

Це результат конкретного сценарію читання, а не максимум продуктивності. Скрипт не вимірює percentiles затримки й не перевіряє всі види операцій під навантаженням.

![Фінальний результат навантажувального тесту](../img/29-load-test-result.png)

### 6.3. Автоматичний scale-out і scale-in

| Подія 2026-11-04 | Час UTC | Europe/Budapest, UTC+01:00 | Результат |
|---|---|---|---|
| AlarmHigh → ScaleUpPolicy | 13:05:34 | 14:05:34 | Desired capacity **1 → 2** |
| Запуск нового EC2 | 13:05:40 | 14:05:40 | i-05dff46be72d3e6fd, Successful |
| AlarmLow → ScaleDownPolicy | 13:24:49 | 14:24:49 | Desired capacity **2 → 1** |
| Виведення додаткового EC2 | 13:25:00 | 14:25:00 | Завершення екземпляра, Successful |

На графіках dashboard вибрано UTC, а в консолі й скрипті зустрічається UTC+01:00. Останній запуск скрипту почався одночасно з подією scale-out; графік також охоплює попереднє навантаження. Тому всю історію CPU не слід приписувати лише цьому запуску. Автоматичний характер переходів підтверджено полем **Cause**, де вказані alarm та policy, а не ручна зміна desired capacity.

![До навантаження: один екземпляр](../img/25-scaling-before.png)

![Зростання CPU і кількості запитів](../img/26-scaling-load.png)

![Scale-out: причина, успішна дія та два екземпляри](../img/28-scaling-after.png)

![Дві цілі Healthy у різних зонах](../img/28-scaling-targets.png)

![Scale-in: причина, успішна дія та повернення до одного екземпляра](../img/30-scaling-final.png)

## 7. План очищення та видалення ресурсів

Очищення заплановано **після захисту проєкту**, коли робочий стенд більше не потрібний. Наведені дії є планом, а не підтвердженням виконаного видалення. Видаляти лише ресурси цього проєкту, перевіряючи назви, VPC та зв’язки із `quotes-env`.

### 7.1. Підготовка

1. Зберегти локально звіт, схему архітектури, скриншоти та код застосунку.
2. За потреби експортувати цитати або створити фінальний snapshot RDS. Збережені snapshots продовжують займати оплачуване сховище.
3. Зафіксувати ID ресурсів, щоб перевірити залишки після видалення Beanstalk. Залишити бюджет активним до завершення перевірки витрат.

### 7.2. Послідовність видалення

| Крок | Ресурси та розділ консолі | Дії й очікуваний результат |
|---|---|---|
| 1 | **Elastic Beanstalk → Environments → quotes-env** | Виконати **Actions → Terminate environment**, дочекатися завершення. Не починати з ручного видалення EC2: Auto Scaling може створити заміну |
| 2 | **EC2 / Auto Scaling / Load Balancing / CloudFormation** | Перевірити видалення EC2 середовища, Auto Scaling Group, ALB, target group, launch template та стека. У разі `DELETE_FAILED` перевірити Events і усунути конкретну залежність. Перевірити непотрібні залишені EBS volumes і snapshots |
| 3 | **RDS → Databases → quotes-db** | За потреби вимкнути deletion protection, виконати Delete. Усвідомлено вибрати, чи зберігати final snapshot та automated backups. Якщо дані більше не потрібні, не залишати їхні копії. Дочекатися видалення БД |
| 4 | **RDS → Snapshots / Automated backups / Subnet groups** | Видалити непотрібні snapshots і retained automated backups проєкту, потім `quotes-db-subnets`. Перевірити також копії в інших регіонах, якщо створювалися |
| 5 | **VPC → NAT gateways; EC2 → Elastic IPs** | Після видалення середовища видалити NAT Gateway і дочекатися стану Deleted. Окремо виконати **Release Elastic IP address** для його виділеної адреси: видалення NAT саме по собі її не звільняє |
| 6 | **Secrets Manager → quotes/database-url** | Запланувати видалення секрету зі строком відновлення, наприклад 7 днів |
| 7 | **CloudWatch → Log groups / Alarms / Dashboards** | Видалити log groups `quotes-env`, alarms та `quotes-dashboard`. У конфігурації вибрано збереження логів після Terminate, тому перевірити їх окремо |
| 8 | **SNS → Topics / Subscriptions** | Видалити `quotes-alerts` та перевірити залишені підписки. Перевірити також службові SNS-ресурси середовища, якщо вони залишилися |
| 9 | **Beanstalk → Applications → quote-collection; S3** | Видалити непотрібні application versions, saved configurations та застосунок. У регіональному бакеті Beanstalk видалити лише ZIP, логи й попередні версії об’єктів проєкту; спільний бакет цілком не очищати |
| 10 | **VPC → Endpoints / Network Interfaces / Security Groups / Your VPCs** | Після звільнення мережевих інтерфейсів видалити S3 gateway endpoint, прибрати взаємні посилання між групами й видалити групи проєкту. Видалити `quotes-vpc` та перевірити пов’язані підмережі, маршрути й Internet Gateway. Default VPC залишити |
| 11 | **IAM → Roles / Instance profiles / Policies** | Видалити виділений профіль і роль `quotes-eb-ec2-role` та inline policy. Видалити `quotes-eb-service-role`, лише якщо вона більше ніде не використовується. AWS managed policies і спільні service-linked roles не видаляти |
| 12 | **Billing → Cost Explorer / Budgets** | Після оновлення білінгу перевірити припинення нових нарахувань за видаленими ресурсами. Видалити непотрібний `fp-budget` або залишити для контролю облікового запису |

Окрема RDS, NAT, Elastic IP, секрет, збережені логи та бюджет не видаляються автоматично разом із середовищем Beanstalk. Керовані мережеві інтерфейси звільняються після видалення батьківського ресурсу; їх не потрібно примусово видаляти.

### 7.3. Фінальна перевірка

- В `us-east-1` немає EC2, Auto Scaling Group, ALB, target group, RDS і NAT цього проєкту.
- Не залишено непотрібних EBS volumes, snapshots, retained backups, Elastic IP та VPC endpoints.
- Перевірено S3, CloudWatch, SNS, Secrets Manager та IAM; збережено лише свідомо потрібні дані або спільні ресурси.
- Після оновлення Cost Explorer перевірено дати використання. Історичні витрати після видалення не зникають; мета — відсутність нових нарахувань за очищеними ресурсами. Перевірку повторити наступного дня та пізніше, якщо дані ще оновлюються.
