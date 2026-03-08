# Aurora

> **A full-featured, production-grade social media platform built with Flask** — supporting posts, reels, stories, live streaming, direct messaging, an integrated shop, creator monetization, advanced AI-driven recommendations, and a powerful admin dashboard.

[![Python](https://img.shields.io/badge/Python-3.11+-blue.svg)](https://www.python.org/)
[![Flask](https://img.shields.io/badge/Flask-3.x-green.svg)](https://flask.palletsprojects.com/)
[![PostgreSQL](https://img.shields.io/badge/PostgreSQL-15-blue.svg)](https://www.postgresql.org/)
[![Redis](https://img.shields.io/badge/Redis-7-red.svg)](https://redis.io/)
[![Celery](https://img.shields.io/badge/Celery-5.x-brightgreen.svg)](https://docs.celeryq.dev/)
[![Docker](https://img.shields.io/badge/Docker-Compose-blue.svg)](https://docs.docker.com/compose/)
[![License: MIT](https://img.shields.io/badge/License-MIT-yellow.svg)](LICENSE)

---

## Table of Contents

- [Project Description](#project-description)
- [Features](#features)
- [Project Architecture](#project-architecture)
- [Project Structure](#project-structure)
- [Technology Stack](#technology-stack)
- [Installation Guide](#installation-guide)
- [Environment Variables](#environment-variables)
- [Database Setup](#database-setup)
- [Running the Application](#running-the-application)
- [API Endpoints](#api-endpoints)
- [Authentication Flow](#authentication-flow)
- [Real-Time Features](#real-time-features)
- [Payments & Monetization](#payments--monetization)
- [Background Tasks](#background-tasks)
- [Deployment Guide](#deployment-guide)
- [Security](#security)
- [Performance Optimization](#performance-optimization)
- [Contributing](#contributing)
- [Testing](#testing)
- [Roadmap](#roadmap)
- [License](#license)
- [Authors](#authors)
- [Acknowledgements](#acknowledgements)
- [Contact](#contact)

---

## Project Description

**Aurora** is a large-scale, Instagram-inspired social media platform built entirely with Python and Flask. It goes far beyond a simple CRUD application — Aurora is a complete, production-ready ecosystem that includes creator monetization tools, a native e-commerce shop, live video streaming, AI-powered content recommendations, advanced content moderation, real-time messaging via WebSockets, and a full-featured admin control panel.

Aurora is designed for developers, startups, and organizations who want a self-hosted social media infrastructure they can fully own, customize, and extend. It demonstrates enterprise-level patterns: modular Blueprint architecture, layered service classes, background task processing via Celery, a Redis-backed pub/sub messaging system, Elasticsearch-powered search, AWS S3 media storage, and Razorpay payment integration.

Whether you are building a niche community, a creator economy platform, or studying how large social platforms are engineered, Aurora provides a thorough, annotated, and runnable reference implementation.

---

## Features

### Authentication & Identity
- Email/password registration with secure bcrypt hashing
- Email verification flow with time-limited tokenized links
- OTP (one-time password) login via email
- Google OAuth 2.0 social login (via Authlib)
- JWT-based session management (stored in secure HttpOnly cookies)
- Account lockout after configurable failed login attempts
- Password reset via email with expiring tokens
- New device login alerts sent via email
- Terms of service acceptance tracking

### User Profiles
- Public and private profile modes
- Professional/creator account type
- Bio with multiple link support
- Profile photo upload (stored on AWS S3 or local fallback)
- Follower/following management with follow request system for private accounts
- User blocking and muting
- User tagging in posts and stories
- Category-based creator classification (Artist, Blogger, Tech, etc.)

### Posts
- Multi-image and video post creation
- Image editing: brightness, contrast, crop adjustments
- Post captions with hashtag and mention parsing
- Location tagging with latitude/longitude
- Branded content disclosure tagging
- Pin post to top of profile
- Archive/unarchive posts
- Hide like counts
- Post editing and deletion

### Reels
- Short-form vertical video upload (MP4, up to 90 seconds and 150MB)
- Video duration and metadata extraction via `hachoir` and `ffprobe`
- Text overlays on reels
- Scheduled reel publishing
- Reel analytics (views, likes, comments, shares)
- Trending reels feed powered by ranking algorithm
- Celery-based deferred publishing

### Stories
- Ephemeral 24-hour stories (images and short videos)
- Story viewer tracking
- Story reactions and replies
- Story highlights (save stories permanently to profile)
- Auto-expiration handled by Celery beat scheduler
- Rate-limited uploads (configurable per hour)

### Feed & Discovery
- Personalized home feed with interest graph-based ranking
- Time-decay scoring with recency half-life algorithm
- Creator quality scoring (follower ratio, verification, activity)
- Explore page: trending posts, trending reels, trending hashtags
- Elasticsearch-powered full-text search (users, posts, hashtags)
- Autocomplete suggestions in search
- Hashtag pages
- Content saved/bookmarked by users

### Direct Messaging
- One-to-one and group conversations
- Real-time message delivery via Flask-SocketIO WebSockets
- Redis pub/sub for horizontal scaling of socket connections
- Message read receipts
- Emoji reactions on messages
- Message requests (from non-followed users)
- Media sharing in messages
- Rate limiting per user (30 messages/minute)

### Notifications
- In-app notification center
- Real-time notification delivery via WebSockets
- Email notification digests
- Notification types: likes, comments, mentions, follows, messages, payments, live alerts, order updates, security events
- Aggregated notifications (e.g., "5 people liked your post")
- Per-user notification preferences

### Live Streaming
- Create and schedule live sessions
- Browse active live sessions
- Live chat with real-time comments and reactions
- Badge gifting during live (Razorpay payment integration)
- Slow mode and comment toggle controls
- Host moderation: mute/remove viewers
- Live guest invitations (up to 3 concurrent guests)
- Live session recording/replay stored on S3

### Broadcast Channels
- Creator-owned broadcast channels
- Channel subscriber management
- Channel update notifications via email

### Engagement
- Like posts, reels, stories, and comments
- Comment on posts and reels with threading (replies)
- Save/bookmark posts
- Share posts externally via public share links

### Shop & Commerce
- Product catalog with categories and inventory tracking
- Product detail pages with media
- Shopping cart and checkout flow
- Wishlist management
- Razorpay-powered checkout
- Order management: confirmation, shipment, delivery, refunds
- Seller dashboard with order overview
- Order tracking for buyers

### Monetization & Creator Economy
- Creator subscription tiers (fan memberships)
- Content boosts/ad campaigns with budget management
- Razorpay-powered payment flow for subscriptions and badges
- Platform commission handling (configurable per transaction type)
- Creator payout requests with minimum payout threshold
- Payout approval workflow in admin
- Affiliate marketing program
- Weekly creator performance report emails

### Business & Ads
- Promoted post/ad campaign creation
- Ad tracking (impressions, clicks, conversions)
- Business analytics dashboard
- Ad spend and revenue reporting

### AI & Algorithms
- AI-generated content captions (via configurable external AI API)
- Content caption caching with TTL
- Interest graph construction and updates from user behavior
- Recommendation engine with collaborative filtering signals
- Ranking service combining recency, creator quality, and user interest

### Moderation
- Automated spam detection service
- Bot detection service
- Content moderation via configurable external moderation API
- Auto-hide flagged content
- User reporting system
- Admin moderation dashboard
- Copyright strike management

### Admin Dashboard
- User management: view, suspend, restore accounts
- Payment and payout management
- Ad campaign oversight
- Moderation queue
- Security audit log viewer
- System health monitoring
- Email broadcast to users
- Compliance reporting

### Settings & Account Management
- Account privacy settings
- Notification preferences
- Connected devices / session management
- Data export (GDPR-style, delivered via email)
- Account deactivation and deletion
- Parental controls with screen time limits
- Theme selection (light/dark)

### Security
- CSRF protection on all forms (Flask-WTF)
- JWT double-submit cookie CSRF protection on APIs
- Rate limiting via Flask-Limiter (Redis-backed in production)
- HSTS headers with configurable max-age
- Content Security Policy (CSP) headers
- X-Frame-Options, X-Content-Type-Options, Referrer-Policy headers
- Rotating file-based security, audit, app, and metrics logs
- RBAC (Role-Based Access Control) for admin panel
- Password strength enforcement
- Account lockout on repeated login failures
- Audit log for all admin actions

---

## Project Architecture

Aurora is organized as a modular monolith using Flask Blueprints. Each domain of the application (auth, posts, reels, messaging, payments, etc.) is a self-contained module with its own routes, services, models, and templates. This structure makes the codebase easy to navigate, test, and extend — and it lays the groundwork for a future migration to microservices if needed.

### Backend Architecture

The backend is structured in three logical layers:

**Route layer** — Flask Blueprint route handlers in `routes.py` files. They are thin: they validate the incoming request, authenticate the user, call into the service layer, and return a response.

**Service layer** — Business logic lives in `*_service.py` or `services.py` files within each module. Services interact with the database through SQLAlchemy models, call external services (Razorpay, AWS S3, Elasticsearch, email), and dispatch Celery tasks.

**Model layer** — SQLAlchemy ORM models in `app/models/`. All database schema is defined here.

### Application Factory

`create_app()` in `app/__init__.py` serves as the application factory. It loads environment configuration, initializes all Flask extensions, registers all Blueprints, sets up Socket.IO namespaces, attaches request middleware for JWT authentication and admin RBAC, and configures rotating log handlers.

### Real-Time Layer

Flask-SocketIO with the `eventlet` async worker powers WebSocket connections. Three Socket.IO namespaces are registered: `/ws/messages` (direct messaging), `/ws/notifications` (notification push), and `/ws/live` (live stream events). Redis pub/sub (via `messaging/redis_pubsub.py`) is used so Socket.IO messages can be broadcast across multiple Gunicorn workers.

### Task Queue

Celery with Redis as the broker handles all deferred and scheduled work. A separate `celery_worker` service runs the worker and a `celery_beat` service manages periodic tasks. Tasks are defined in `tasks.py` files within each module.

### Search

Elasticsearch is the search backend for full-text user, post, and hashtag search. The `algorithms/search_service.py` module manages index writes and query execution. Index names are prefixed (default: `aurora`) to allow multi-tenant or multi-environment deployments.

### Storage

Media files (profile photos, post images, reel videos, story media) are uploaded to AWS S3. In development or when AWS credentials are absent, a local filesystem fallback (`local_uploads/`) is used and files are served directly by Flask.

### Payments

Razorpay handles all monetary transactions: live badge purchases, creator subscriptions, product checkouts, and ad campaign payments. Webhook verification ensures only authentic Razorpay events update order and payment state.

---

## Project Structure

```
Aurora/
├── app/
│   ├── __init__.py                  # Application factory, blueprint registration, middleware
│   ├── config.py                    # DevelopmentConfig, ProductionConfig, TestingConfig
│   ├── extensions.py                # Flask extension instances (db, jwt, celery, socketio, etc.)
│   │
│   ├── models/                      # SQLAlchemy ORM models
│   │   ├── user.py                  # User, Follow, Block, Mute, BioLink, OAuthAccount
│   │   ├── post.py                  # Post, PostMedia, Comment, Like, Hashtag, Location, SavedPost
│   │   ├── reel.py                  # Reel, ReelInsight, ReelComment, ReelHashtag
│   │   ├── story.py                 # Story, StoryView, StoryReaction, StoryHighlight
│   │   ├── messaging.py             # Conversation, Message, MessageReaction, MessageRequest
│   │   ├── notification.py          # Notification
│   │   ├── live.py                  # LiveSession, LiveComment, LiveReaction, LiveParticipant, LiveBadgeTransaction, LiveModerationAction
│   │   ├── broadcast.py             # BroadcastChannel, ChannelSubscriber
│   │   ├── commerce.py              # Product, Cart, CartItem, Order, OrderItem, Wishlist
│   │   ├── payment.py               # PaymentTransaction
│   │   ├── monetization.py          # CreatorSubscription, BoostCampaign, AffiliateConversion
│   │   ├── ad.py                    # AdCampaign, AdImpression
│   │   ├── analytics.py             # AnalyticsEvent
│   │   ├── intelligence.py          # InterestGraph
│   │   ├── moderation.py            # Report, ContentFlag, CopyrightStrike
│   │   ├── security.py              # RBACRole, AdminUser, AuditLog, LoginRecord, DeviceSession
│   │   ├── settings.py              # UserSettings, NotificationPreference
│   │   └── email.py                 # EmailLog
│   │
│   ├── core/                        # Shared utilities
│   │   ├── security.py              # Security headers, password validation, CSP
│   │   ├── storage.py               # AWS S3 upload/download, signed URL generation, local fallback
│   │   ├── tokens.py                # Itsdangerous token signing for email verification/reset
│   │   ├── email.py                 # Low-level email send helpers
│   │   └── errors.py                # Error response builder, error handler registration
│   │
│   ├── auth/                        # Authentication module
│   │   ├── routes.py                # /signup, /login, /logout, /verify-email, /forgot-password, /reset-password, /verify-otp, /google OAuth
│   │   └── forms.py                 # SignupForm, LoginForm, PasswordResetForms, VerifyOTPForm
│   │
│   ├── users/                       # User profiles and relationships
│   │   ├── routes.py                # Profile view, edit, follow/unfollow, block, mute, search
│   │   └── forms.py                 # ProfileEditForm
│   │
│   ├── posts/                       # Posts module
│   │   ├── routes.py                # Create, view, edit, delete, archive, pin
│   │   ├── services.py              # Post creation, media processing, hashtag parsing
│   │   ├── media_utils.py           # Image processing with Pillow (crop, brightness, contrast)
│   │   └── forms.py                 # PostCreateForm, PostEditForm
│   │
│   ├── reels/                       # Short-form video
│   │   ├── routes.py                # Create, feed, detail, delete
│   │   ├── services.py              # Upload, publish, scheduling logic
│   │   ├── video_utils.py           # ffprobe metadata extraction, duration validation
│   │   ├── analytics.py             # Reel view and insight recording
│   │   └── tasks.py                 # publish_reel_task, refresh_trending_task
│   │
│   ├── stories/                     # Ephemeral stories
│   │   ├── routes.py                # Create, list, view, highlight, delete
│   │   ├── services.py              # Story upload, expiry, viewer tracking, reactions
│   │   └── tasks.py                 # expire_stories_task
│   │
│   ├── feed/                        # Home feed
│   │   ├── routes.py                # /feed
│   │   └── services.py              # Feed assembly using ranking scores
│   │
│   ├── explore/                     # Explore and trending
│   │   ├── routes.py                # /explore, /search
│   │   ├── services.py              # Trending posts, hashtags, reels
│   │   └── tasks.py                 # Periodic trending refresh
│   │
│   ├── engagement/                  # Likes, comments, saves, shares
│   │   ├── routes.py                # Toggle like, add/delete comment, save post
│   │   └── services.py             # Engagement logic, notification dispatch
│   │
│   ├── messaging/                   # Direct messaging
│   │   ├── routes.py                # Inbox, conversation, send message, message requests
│   │   ├── messaging_service.py     # Conversation/message CRUD, membership checks
│   │   ├── socket_events.py         # /ws/messages namespace: connect, send, typing, read
│   │   ├── redis_pubsub.py          # Redis pub/sub channel helpers for horizontal scaling
│   │   └── message_utils.py         # Message formatting utilities
│   │
│   ├── notifications/               # Notification system
│   │   ├── routes.py                # /notifications
│   │   ├── notification_service.py  # Notification CRUD
│   │   ├── notification_dispatcher.py # Fan-out: in-app + socket + email + FCM
│   │   ├── notification_preferences.py # Per-user preference checks
│   │   ├── notification_templates.py   # Notification text/link templates
│   │   ├── socket_events.py         # /ws/notifications namespace
│   │   └── tasks.py                 # Async notification delivery
│   │
│   ├── live/                        # Live streaming
│   │   ├── routes.py                # Create, browse, view session, badge purchase, moderation
│   │   ├── live_service.py          # Schedule, start, end session, comments, reactions, moderation
│   │   ├── streaming_service.py     # Streaming session state management
│   │   ├── socket_events.py         # /ws/live namespace: join, leave, comment, react
│   │   └── tasks.py                 # Live session cleanup tasks
│   │
│   ├── broadcast/                   # Broadcast channels
│   │   ├── routes.py                # Create channel, subscribe, post updates
│   │   └── services.py              # Channel and subscriber management
│   │
│   ├── sharing/                     # Public share links
│   │   ├── routes.py                # /share/<token> public post view
│   │   └── services.py              # Share token generation and resolution
│   │
│   ├── recommendation/              # Recommendation engine
│   │   ├── routes.py                # /recommendations
│   │   └── services.py              # Trending and personalized content computation
│   │
│   ├── algorithms/                  # Core ranking and AI
│   │   ├── ranking_service.py       # Recency decay, creator quality, interest-weighted scoring
│   │   ├── interest_graph_service.py # Build and update user interest graph from behavior
│   │   ├── search_service.py        # Elasticsearch index management, query execution, autocomplete
│   │   ├── ai_content_service.py    # AI caption generation via external API
│   │   ├── recommendation_cache.py  # Redis-backed recommendation result caching
│   │   ├── listeners.py             # SQLAlchemy event listeners for search index updates
│   │   └── tasks.py                 # Background indexing and graph computation tasks
│   │
│   ├── moderation/                  # Content moderation
│   │   ├── routes.py                # Report content, view reports
│   │   ├── moderation_service.py    # Report handling, auto-hide, strike management
│   │   ├── spam_detection_service.py # Heuristic spam detection
│   │   ├── bot_detection_service.py  # Bot behavior detection
│   │   └── tasks.py                 # Periodic moderation sweep tasks
│   │
│   ├── business/                    # Business accounts and ads
│   │   ├── routes.py                # Ad campaign creation, analytics
│   │   ├── ads_tracking.py          # Ad impression and click tracking
│   │   ├── analytics_service.py     # Business analytics aggregation
│   │   └── tasks.py                 # Analytics rollup tasks
│   │
│   ├── monetization/                # Creator monetization
│   │   ├── routes.py                # Subscriptions, marketplace, badge purchases
│   │   ├── monetization_service.py  # Subscription creation, affiliate conversion, webhook handling
│   │   └── tasks.py                 # Subscription renewal, payout eligibility checks
│   │
│   ├── payments/                    # Payment processing
│   │   ├── routes.py                # /order, /capture, /webhook, /payout
│   │   ├── razorpay_service.py      # Razorpay order creation, signature verification
│   │   ├── payout_service.py        # Creator payout request and processing
│   │   └── tasks.py                 # Payout status polling tasks
│   │
│   ├── shop/                        # Product catalog
│   │   └── routes.py                # Catalog, product detail, wishlist
│   │
│   ├── commerce/                    # Cart and checkout
│   │   ├── routes.py                # Cart management, Razorpay checkout
│   │   ├── cart_service.py          # Add/remove/update cart items
│   │   ├── product_service.py       # Product CRUD and inventory
│   │   ├── order_service.py         # Order creation and state machine
│   │   ├── inventory_service.py     # Stock management
│   │   ├── razorpay_checkout_service.py # Commerce-specific Razorpay order creation
│   │   ├── webhooks.py              # Commerce webhook handler
│   │   └── tasks.py                 # Order status update tasks
│   │
│   ├── orders/                      # Order management UI
│   │   └── routes.py                # Order history, tracking, seller dashboard
│   │
│   ├── affiliate/                   # Affiliate marketing
│   │   ├── routes.py                # Affiliate dashboard, link generation
│   │   └── affiliate_service.py     # Referral tracking and conversion recording
│   │
│   ├── admin/                       # Admin control panel
│   │   ├── routes.py                # Dashboard, users, payments, ads, moderation, security, system
│   │   ├── compliance_service.py    # GDPR/compliance data handling
│   │   ├── moderation_dashboard_service.py # Admin moderation queue
│   │   └── monitoring_service.py    # System health metrics collection
│   │
│   ├── security/                    # Security and RBAC
│   │   ├── routes.py                # Security center, audit log viewer
│   │   ├── rbac_service.py          # Role-based access control, admin bootstrapping
│   │   ├── audit_log_service.py     # Admin action audit logging
│   │   └── validation.py            # Input validation helpers
│   │
│   ├── settings/                    # Account settings
│   │   ├── routes.py                # Privacy, notifications, sessions, data export, deactivation
│   │   ├── services.py              # Settings CRUD, device session management
│   │   └── tasks.py                 # Data export packaging and delivery
│   │
│   ├── email/                       # Transactional email
│   │   ├── email_service.py         # Jinja2 template rendering, Flask-Mail delivery, priority queuing
│   │   └── templates/               # HTML email templates organized by category
│   │       ├── auth/                # Verification, password reset, OTP, login alert
│   │       ├── social/              # Follow, like, comment, mention, DM notifications
│   │       ├── commerce/            # Order confirmation, shipment, payment, refund
│   │       ├── monetization/        # Subscription, badge, payout, boost campaign emails
│   │       ├── reports/             # Weekly activity summary, creator performance
│   │       ├── broadcast/           # Channel update notifications
│   │       └── system/              # Data export ready notification
│   │
│   ├── system/                      # System utilities
│   │   └── routes.py                # /health endpoint, system diagnostics
│   │
│   ├── static/                      # Static assets
│   │   ├── css/main.css
│   │   ├── js/main.js               # Core UI interactions
│   │   ├── js/realtime.js           # Socket.IO client initialization
│   │   └── js/razorpay.js           # Razorpay checkout integration
│   │
│   └── templates/                   # Jinja2 HTML templates organized by blueprint
│
├── docker/
│   └── nginx.conf                   # Nginx reverse proxy with SSL, HSTS, CSP, WebSocket upgrade
│
├── logs/                            # Rotating log files (app, security, audit, metrics)
│
├── Dockerfile                       # Multi-stage Docker build
├── docker-compose.yml               # Full stack: web, celery_worker, celery_beat, db, redis, nginx
├── gunicorn.conf.py                 # Gunicorn: eventlet workers, CPU-scaled concurrency
├── celery_worker.py                 # Celery app entry point
├── wsgi.py                          # WSGI entry point
├── requirements.txt                 # Python dependencies
└── .env.example                     # Environment variable template
```

---

## Technology Stack

| Layer | Technology |
|---|---|
| Language | Python 3.11+ |
| Web Framework | Flask 3.x |
| Database | PostgreSQL 15 (SQLite in development) |
| ORM | Flask-SQLAlchemy + Flask-Migrate (Alembic) |
| Authentication | Flask-JWT-Extended (cookie-based JWT) + Flask-Bcrypt |
| OAuth | Authlib (Google OAuth 2.0) |
| Real-Time | Flask-SocketIO + eventlet |
| Task Queue | Celery 5.x |
| Message Broker | Redis 7 |
| Caching | Redis |
| Search | Elasticsearch 8.x |
| Media Storage | AWS S3 (boto3) / Local filesystem fallback |
| Media Processing | Pillow (images), MoviePy + ffmpeg (video), hachoir (metadata) |
| Payments | Razorpay |
| Email | Flask-Mail (SMTP) |
| Push Notifications | Firebase Cloud Messaging (FCM) |
| Rate Limiting | Flask-Limiter (Redis-backed) |
| CSRF Protection | Flask-WTF |
| Forms | WTForms |
| CORS | Flask-Cors |
| Web Server | Gunicorn (eventlet worker) |
| Reverse Proxy | Nginx 1.25 (SSL/TLS, HTTP/2, WebSocket proxy) |
| Containerization | Docker + Docker Compose |
| Logging | Python `logging` with RotatingFileHandler |

---

## Installation Guide

### Prerequisites

Before installing Aurora, ensure the following are available on your system:

- **Python 3.11 or higher**
- **pip** (Python package manager)
- **Git**
- **Docker and Docker Compose** (recommended for full-stack deployment)
- **PostgreSQL 15** (if running without Docker)
- **Redis 7** (if running without Docker)
- **ffmpeg** (required for reel video processing)

### Local Development Setup (without Docker)

#### 1. Clone the Repository

```bash
git clone https://github.com/shahram8708/Aurora.git
cd Aurora
```

#### 2. Create and Activate a Virtual Environment

```bash
python3 -m venv venv
source venv/bin/activate      # Linux / macOS
venv\Scripts\activate         # Windows
```

#### 3. Install Python Dependencies

```bash
pip install -r requirements.txt
```

#### 4. Install System Dependencies

Aurora requires `ffmpeg` for video processing:

```bash
# Ubuntu/Debian
sudo apt-get update && sudo apt-get install -y ffmpeg

# macOS (via Homebrew)
brew install ffmpeg

# Windows
# Download from https://ffmpeg.org/download.html and add to PATH
```

#### 5. Copy and Configure the Environment File

```bash
cp .env.example .env
```

Edit `.env` and fill in your values. See the [Environment Variables](#environment-variables) section for full details.

#### 6. Set Up the Database

```bash
flask db upgrade
```

#### 7. Start the Development Server

```bash
flask run
```

The application will be available at `http://localhost:5000`.

### Full Stack with Docker Compose

The recommended way to run Aurora with all services (PostgreSQL, Redis, Celery, Nginx) is Docker Compose:

```bash
git clone https://github.com/shahram8708/Aurora.git
cd Aurora
cp .env.example .env
# Edit .env with production values
docker-compose up --build
```

This starts:
- `web` — Gunicorn + Flask application on port 5000
- `celery_worker` — Celery background worker (4 concurrent processes)
- `celery_beat` — Celery periodic task scheduler
- `db` — PostgreSQL 15 on port 5432
- `redis` — Redis 7 on port 6379
- `nginx` — Nginx reverse proxy on ports 80 and 443

---

## Environment Variables

Copy `.env.example` to `.env` and configure each variable:

### Core Application

```env
FLASK_ENV=development          # Environment: development | production | testing
FLASK_APP=wsgi.py              # Entry point for Flask CLI
SECRET_KEY=your-secret-key     # Flask secret key for session signing — use a long random string
```

### Database

```env
DATABASE_URL=postgresql://social_user:supersecret@localhost:5432/social
# SQLite fallback for development: sqlite:///app/social.db
TEST_DATABASE_URL=sqlite:///:memory:
```

### JWT Authentication

```env
JWT_SECRET_KEY=your-jwt-secret    # Secret for signing JWT tokens
JWT_ACCESS_MINUTES=15             # Access token lifetime in minutes (default: 365 days if unset)
JWT_REFRESH_DAYS=30               # Refresh token lifetime in days
```

### Redis

```env
REDIS_URL=redis://localhost:6379/0   # Redis connection string
```

### Email (SMTP)

```env
MAIL_SERVER=smtp.gmail.com
MAIL_PORT=587
MAIL_USE_TLS=true
MAIL_USERNAME=your-email@example.com
MAIL_PASSWORD=your-app-password
MAIL_DEFAULT_SENDER=no-reply@example.com
```

### Google OAuth

```env
GOOGLE_CLIENT_ID=your-google-client-id
GOOGLE_CLIENT_SECRET=your-google-client-secret
GOOGLE_REDIRECT_URI=https://aurora-ind.onrender.com/google/callback
```

### AWS S3

```env
AWS_ACCESS_KEY_ID=your-aws-access-key-id
AWS_SECRET_ACCESS_KEY=your-aws-secret-access-key
AWS_S3_BUCKET=your-bucket-name
AWS_S3_REGION=us-east-1
AWS_S3_SIGNED_TTL=3600           # Presigned URL TTL in seconds
```

### Razorpay Payments

```env
RAZORPAY_KEY_ID=your-razorpay-key-id
RAZORPAY_KEY_SECRET=your-razorpay-key-secret
RAZORPAY_WEBHOOK_SECRET=your-webhook-signing-secret
```

### Elasticsearch

```env
ELASTICSEARCH_URL=http://localhost:9200
ELASTICSEARCH_USERNAME=                    # Optional: basic auth
ELASTICSEARCH_PASSWORD=
SEARCH_INDEX_PREFIX=aurora                 # Index name prefix
```

### Celery

```env
CELERY_BROKER_URL=redis://localhost:6379/0
CELERY_RESULT_BACKEND=redis://localhost:6379/0
```

### Admin Account (Auto-Bootstrapped)

```env
ADMIN_EMAIL=admin@example.com
ADMIN_USERNAME=admin_user
ADMIN_PASSWORD=change-me-to-a-strong-password
ADMIN_NAME=Admin User
```

### Logging

```env
LOG_DIR=logs
LOG_LEVEL=INFO
```

### Security

```env
SESSION_COOKIE_SECURE=true     # Set false for HTTP development
HSTS_ENABLED=true
HSTS_MAX_AGE=31536000
```

### Platform Configuration

```env
PLATFORM_COMMISSION_RATE=0.1       # 10% platform commission on creator revenue
MIN_PAYOUT_AMOUNT=5000             # Minimum payout in smallest currency unit (e.g., paise for INR)
REEL_MAX_DURATION_SEC=90
REEL_MAX_SIZE_MB=150
STORY_MAX_DURATION_SEC=30
AGE_MINIMUM=13
```

### Feature Flags

```env
USE_REDIS=true               # Set false in development to skip Redis
USE_CELERY=true              # Set false in development to skip Celery
USE_AWS=true                 # Set false to use local file storage
USE_ELASTICSEARCH=true       # Set false to skip Elasticsearch
USE_DOCKER_SERVICES=true
```

---

## Database Setup

Aurora uses Flask-Migrate (backed by Alembic) for database schema management.

### Initialize and Apply Migrations

```bash
# Apply all existing migrations to create the schema
flask db upgrade
```

### Create a New Migration (after model changes)

```bash
flask db migrate -m "Description of schema change"
flask db upgrade
```

### Reset the Database (development only)

```bash
flask db downgrade base
flask db upgrade
```

### Admin Account Bootstrap

An admin account is automatically created on first startup if the `ADMIN_EMAIL`, `ADMIN_USERNAME`, and `ADMIN_PASSWORD` environment variables are set. The bootstrap logic is idempotent — it will not create duplicates on subsequent restarts.

---

## Running the Application

### Development Server

```bash
flask run
```

The application runs on `http://localhost:5000` with debug mode enabled. In development, Redis, Celery, Elasticsearch, and AWS are disabled by default (controlled via feature flags in `DevelopmentConfig`). This allows the application to run with SQLite and no external services.

### Background Worker (required for emails, notifications, story expiry, video processing)

```bash
celery -A celery_worker.celery worker --loglevel=info --concurrency=4 -Q default
```

### Celery Beat Scheduler (required for periodic tasks)

```bash
celery -A celery_worker.celery beat --loglevel=info
```

### Production with Gunicorn

```bash
gunicorn wsgi:app
```

Gunicorn configuration is in `gunicorn.conf.py`. It binds to `0.0.0.0:5000`, uses `eventlet` as the worker class (required for Socket.IO), and scales workers to `(CPU count × 2) + 1`.

### Docker Compose (Full Stack)

```bash
docker-compose up --build -d
```

To view logs:

```bash
docker-compose logs -f web
docker-compose logs -f celery_worker
```

To stop all services:

```bash
docker-compose down
```

---

## API Endpoints

Aurora serves both HTML pages (server-rendered Jinja2 templates) and JSON API endpoints. JWT authentication is required for all protected endpoints (passed as a cookie `access_token_cookie` or as a `Bearer` token in the `Authorization` header).

### Authentication

| Method | Endpoint | Description |
|---|---|---|
| GET/POST | `/signup` | Create a new account |
| GET/POST | `/login` | Log in with email + password |
| POST | `/logout` | Invalidate JWT cookies |
| GET | `/verify-email?token=<token>` | Verify email address |
| GET/POST | `/forgot-password` | Request password reset email |
| GET/POST | `/reset-password?token=<token>` | Reset password |
| GET/POST | `/verify-otp` | Verify login OTP |
| GET | `/auth/google` | Initiate Google OAuth flow |
| GET | `/auth/google/callback` | Google OAuth callback |

### Posts

| Method | Endpoint | Description |
|---|---|---|
| GET/POST | `/create` | Create a new post |
| GET | `/posts/<post_id>` | View a post |
| POST | `/posts/<post_id>/edit` | Edit post caption |
| POST | `/posts/<post_id>/delete` | Delete a post |
| POST | `/posts/<post_id>/archive` | Toggle archive status |
| POST | `/posts/<post_id>/pin` | Toggle pin to profile |

### Engagement

| Method | Endpoint | Description |
|---|---|---|
| POST | `/like/<content_type>/<content_id>` | Toggle like on post, reel, comment, or story |
| POST | `/comment/<post_id>` | Add a comment |
| DELETE | `/comment/<comment_id>` | Delete a comment |
| POST | `/save/<post_id>` | Toggle save/bookmark |

### Reels

| Method | Endpoint | Description |
|---|---|---|
| GET/POST | `/reels/create` | Upload a new reel |
| GET | `/reels/feed` | Reels feed |
| GET | `/reels/<reel_id>` | View a single reel |
| POST | `/reels/<reel_id>/delete` | Delete a reel |

### Stories

| Method | Endpoint | Description |
|---|---|---|
| GET/POST | `/stories/create` | Create a story |
| GET | `/stories` | List active stories from followed users |
| GET | `/stories/viewer/<story_id>` | View a story |
| GET | `/stories/highlights` | View story highlights |

### Messaging

| Method | Endpoint | Description |
|---|---|---|
| GET | `/messages` | Inbox |
| GET | `/messages/<conversation_id>` | View conversation |
| POST | `/messages/<conversation_id>/send` | Send a message |
| GET | `/messages/requests` | Message requests from non-followers |

### Notifications

| Method | Endpoint | Description |
|---|---|---|
| GET | `/notifications` | Notification list |
| POST | `/notifications/<id>/read` | Mark notification as read |
| POST | `/notifications/read-all` | Mark all as read |

### Payments

| Method | Endpoint | Description |
|---|---|---|
| POST | `/payments/order` | Create a Razorpay order |
| POST | `/payments/capture` | Capture payment after Razorpay success |
| POST | `/payments/webhook` | Razorpay webhook endpoint (exempt from CSRF) |
| POST | `/payments/payout` | Request creator payout |

### Commerce (Shop)

| Method | Endpoint | Description |
|---|---|---|
| GET | `/shop/catalog` | Browse product catalog |
| GET | `/shop/products/<product_id>` | Product detail page |
| GET/POST | `/shop/wishlist` | View and manage wishlist |
| POST | `/commerce/cart/add` | Add item to cart |
| POST | `/commerce/cart/update` | Update cart item quantity |
| POST | `/commerce/cart/remove` | Remove item from cart |
| GET | `/commerce/checkout` | Checkout page |
| GET | `/orders/history` | Order history |
| GET | `/orders/tracking/<order_id>` | Track an order |
| GET | `/orders/seller` | Seller dashboard |

### Live Streaming

| Method | Endpoint | Description |
|---|---|---|
| GET | `/live/create` | Create live session page |
| POST | `/live/start` | Start a live session |
| POST | `/live/end/<session_id>` | End a live session |
| GET | `/live/browse` | Browse active live sessions |
| GET | `/live/<session_id>` | View a live session |
| POST | `/live/<session_id>/badge` | Purchase a badge during live |

### Admin Panel

| Method | Endpoint | Description |
|---|---|---|
| GET | `/admin/dashboard` | Admin overview |
| GET | `/admin/users` | User management |
| POST | `/admin/users/<id>/suspend` | Suspend a user account |
| POST | `/admin/users/<id>/restore` | Restore a user account |
| GET | `/admin/payments` | Payment overview |
| GET | `/admin/payouts` | Payout management |
| POST | `/admin/payouts/<id>/approve` | Approve a creator payout |
| GET | `/admin/moderation` | Moderation queue |
| GET | `/admin/security` | Security audit log |
| GET | `/admin/system` | System health metrics |

### Utility

| Method | Endpoint | Description |
|---|---|---|
| GET | `/health` | Health check — returns `{"status": "ok"}` |

---

## Authentication Flow

### Standard Registration

1. User submits the signup form (`/signup`) with email, username, password, and name.
2. Flask-WTF validates the form. The password is checked against complexity requirements.
3. A new `User` record is created with a bcrypt-hashed password.
4. A signed `EmailVerificationToken` is generated using Itsdangerous and emailed to the user.
5. User clicks the verification link (`/verify-email?token=<token>`).
6. On success, `email_verified` is set to `True` on the user record.

### Login

1. User submits login credentials (`/login`).
2. User is looked up by email or username. If the account is locked (after `MAX_FAILED_LOGINS` failures), login is rejected with a lockout message.
3. If 2FA is required, a random OTP is generated, stored in the session, and emailed to the user.
4. User enters the OTP at `/verify-otp`. On success, JWT access and refresh tokens are generated.
5. Tokens are set as secure, HttpOnly cookies (`access_token_cookie`, `refresh_token_cookie`).
6. A new device login alert email is dispatched if the device fingerprint has not been seen before.

### Google OAuth Login

1. User clicks "Sign in with Google" → redirected to `/auth/google`.
2. Authlib constructs the Google OAuth authorization URL and redirects the user.
3. Google redirects to `/auth/google/callback` with an authorization code.
4. Authlib exchanges the code for tokens and fetches the user's Google profile.
5. If a matching `OAuthAccount` is found, the user is logged in. If not, a new `User` and `OAuthAccount` are created.
6. JWT cookies are set and the user is redirected to the feed.

### Session Management

- JWT access tokens are stored in `access_token_cookie` (HttpOnly, Secure, SameSite=Lax).
- Refresh tokens are stored in `refresh_token_cookie`.
- All protected routes use `@jwt_required()`. The current user is loaded into `g.current_user` by `load_request_user()` middleware before each request.
- On token expiry, Flask-JWT-Extended redirects to the login page with a flash message.
- On logout, `unset_jwt_cookies()` clears both cookies.

---

## Real-Time Features

Aurora uses **Flask-SocketIO** with **eventlet** for async WebSocket support. Three Socket.IO namespaces are active:

### Direct Messaging (`/ws/messages`)

Defined in `app/messaging/socket_events.py`.

- **connect**: Client authenticates by sending a JWT in the `Authorization` header, query string, or cookie. Identity is extracted using `decode_token`.
- **join_conversation**: Client joins a room named after the conversation UUID.
- **send_message**: Emits `new_message` to all members of the conversation room. The message is persisted via `messaging_service.save_message()`. A notification is dispatched to offline recipients.
- **typing**: Broadcasts a `typing` event to conversation room members (excluding sender).
- **read_messages**: Marks all unread messages as read; emits `messages_read` to the sender.
- **Rate limiting**: Redis tracks per-user message rate. Users exceeding 30 messages/minute receive an error.

Redis pub/sub (via `redis_pubsub.py`) is used to fan out events across all Gunicorn workers, ensuring messages are delivered even when sender and receiver are connected to different processes.

### Notifications (`/ws/notifications`)

Defined in `app/notifications/socket_events.py`.

- **connect**: User joins a room named after their user UUID.
- On notification dispatch, `notification_dispatcher.py` calls `socketio.emit()` to the user's room with the notification payload.

### Live Streaming (`/ws/live`)

Defined in `app/live/socket_events.py`.

- **join_live**: Client joins a room for the live session. Viewer count is incremented in Redis.
- **live_comment**: New comment is broadcast to the session room and persisted.
- **live_reaction**: Reaction is broadcast to all viewers.
- **leave_live**: Viewer count decremented. Session ended if host leaves.

---

## Payments & Monetization

### Razorpay Integration

All payments flow through Razorpay. The integration is in `app/payments/razorpay_service.py`.

**Order Creation (`POST /payments/order`)**

```json
Request:
{
  "amount": 49900,
  "purpose": "subscription",
  "receipt": "sub_user123",
  "notes": {}
}

Response:
{
  "id": "order_XXXXXXXXXXXXXX",
  "amount": 49900,
  "currency": "INR"
}
```

**Payment Capture (`POST /payments/capture`)**

After the Razorpay checkout widget completes:
```json
Request:
{
  "order_id": "order_XXXXXXXXXXXXXX",
  "payment_id": "pay_YYYYYYYYYYYYYY",
  "signature": "<razorpay_signature>"
}
```

The server verifies the HMAC SHA256 signature using `RAZORPAY_KEY_SECRET`. On success, the `PaymentTransaction` record is updated to `"paid"` and a payment success notification is dispatched.

**Webhook (`POST /payments/webhook`)**

Razorpay sends signed webhook events for payment updates. The endpoint verifies the `X-Razorpay-Signature` header before processing. Supported events include `payment.captured`, `payment.failed`, and subscription renewal events. This endpoint is exempt from CSRF protection.

### Creator Monetization

- **Subscriptions**: Fans can subscribe to a creator's tier. Managed by `monetization_service.py`. Subscription payments go through Razorpay; the platform retains a configurable commission (default 15%).
- **Live Badges**: Viewers can purchase virtual badges during a live stream. Badge revenue is split between the creator and the platform (default 10% fee).
- **Content Boosts**: Creators can pay to boost posts/reels to a wider audience. Ad spend is tracked per campaign.
- **Affiliate Program**: Affiliate links are generated per user. Conversions are tracked via `affiliate_service.py`.
- **Payouts**: Creators request payouts via `POST /payments/payout`. Admin approves via the admin panel. Minimum payout threshold is configurable (`MIN_PAYOUT_AMOUNT`).

---

## Background Tasks

Aurora uses Celery for all deferred and periodic work. Tasks are defined in `tasks.py` files within each module and registered with the shared Celery instance from `app/extensions.py`.

### Key Tasks

| Task | Module | Description |
|---|---|---|
| `publish_reel_task` | `reels` | Publishes a scheduled reel at the specified time |
| `refresh_trending_task` | `reels` | Recomputes trending reels scores |
| `expire_stories_task` | `stories` | Marks stories older than 24 hours as expired |
| `send_email_task` | `notifications` | Async email delivery |
| `notification_delivery_task` | `notifications` | Fan-out notification to in-app, socket, email, FCM |
| `analytics_rollup_task` | `business` | Aggregate ad analytics data |
| `subscription_renewal_task` | `monetization` | Process recurring subscription renewals |
| `payout_status_task` | `payments` | Poll Razorpay for payout status updates |
| `compute_interest_graph_task` | `algorithms` | Rebuild user interest graphs from recent behavior |
| `search_index_task` | `algorithms` | Index new/updated content in Elasticsearch |
| `moderation_sweep_task` | `moderation` | Periodic automated content moderation sweep |
| `explore_refresh_task` | `explore` | Refresh trending content cache |
| `data_export_task` | `settings` | Package and upload user data export to S3 |
| `order_status_task` | `commerce` | Update order statuses and trigger notifications |

### Running Workers

```bash
# Worker
celery -A celery_worker.celery worker --loglevel=info --concurrency=4 -Q default

# Beat scheduler
celery -A celery_worker.celery beat --loglevel=info

# Flower monitoring (optional)
pip install flower
celery -A celery_worker.celery flower --port=5555
```

---

## Deployment Guide

### Docker Compose (Recommended)

```bash
# Clone and configure
git clone https://github.com/shahram8708/Aurora.git
cd Aurora
cp .env.example .env
# Edit .env: set FLASK_ENV=production, strong SECRET_KEY, DATABASE_URL, REDIS_URL, etc.

# Build and start
docker-compose up --build -d

# Apply database migrations
docker-compose exec web flask db upgrade

# View status
docker-compose ps
```

### SSL Certificates

The Nginx configuration expects SSL certificates at:

```
/etc/ssl/certs/fullchain.pem
/etc/ssl/private/privkey.pem
```

For Let's Encrypt, use Certbot:

```bash
certbot certonly --standalone -d yourdomain.com
```

Mount the certificates into the Nginx container by updating the volume in `docker-compose.yml`.

### Nginx Configuration

The provided `docker/nginx.conf` configures:
- HTTP → HTTPS redirect on port 80
- TLS 1.2 and 1.3 only
- HTTP/2
- HSTS with 1-year max-age
- Content Security Policy headers
- WebSocket proxy (`Upgrade: websocket`) for Socket.IO
- Rate limiting: 10 requests/second with a burst of 20
- Static file serving with 30-day cache headers
- Proxy pass to Gunicorn on port 5000

### Gunicorn Configuration

`gunicorn.conf.py` key settings:

```python
bind = "0.0.0.0:5000"
workers = multiprocessing.cpu_count() * 2 + 1
worker_class = "eventlet"    # Required for Socket.IO
timeout = 120
keepalive = 5
graceful_timeout = 90
```

### AWS Deployment

For production AWS deployment:

1. **EC2**: Launch an instance (t3.medium or larger). Install Docker. Clone the repo and run via Docker Compose.
2. **RDS**: Create a PostgreSQL 15 instance. Set `DATABASE_URL` in `.env`.
3. **ElastiCache**: Create a Redis 7 cluster. Set `REDIS_URL` in `.env`.
4. **S3**: Create a bucket for media uploads. Set `AWS_S3_BUCKET`, `AWS_ACCESS_KEY_ID`, `AWS_SECRET_ACCESS_KEY`.
5. **Elasticsearch Service (Amazon OpenSearch)**: Create a domain. Set `ELASTICSEARCH_URL`.
6. **ACM**: Request an SSL certificate for your domain and configure it with your load balancer or Nginx.
7. **Application Load Balancer**: Place in front of EC2 instances for horizontal scaling. Configure sticky sessions or use Redis for session sharing.

### Environment Variable Checklist for Production

- `FLASK_ENV=production`
- `SECRET_KEY` — long, random, unique
- `JWT_SECRET_KEY` — long, random, unique
- `DATABASE_URL` — PostgreSQL connection string
- `REDIS_URL` — Redis connection string
- `SESSION_COOKIE_SECURE=true`
- `HSTS_ENABLED=true`
- `USE_REDIS=true`
- `USE_CELERY=true`
- `USE_AWS=true`
- `USE_ELASTICSEARCH=true`
- All AWS credentials
- All Razorpay credentials
- `ADMIN_PASSWORD` — strong unique password

---

## Security

Aurora implements defense-in-depth with multiple overlapping security layers:

### Authentication & Session Security
- Passwords hashed with bcrypt (work factor configurable)
- JWT tokens stored in HttpOnly, Secure, SameSite=Lax cookies — inaccessible to JavaScript
- JWT double-submit cookie CSRF protection on API endpoints
- Flask-WTF CSRF tokens on all HTML form submissions
- Account lockout after `MAX_FAILED_LOGINS` failed attempts (default: 5), with 15-minute lock window
- Password complexity enforcement via `is_strong_password()` in `core/security.py`
- New device login email alert

### Transport Security
- HTTPS enforced via Nginx HTTP→HTTPS redirect
- HSTS header (`Strict-Transport-Security: max-age=31536000; includeSubDomains`)
- TLS 1.2+ only; weak ciphers disabled in Nginx
- HTTP/2 enabled

### HTTP Security Headers
All responses include (applied in `core/security.py`):
- `X-Content-Type-Options: nosniff`
- `X-Frame-Options: SAMEORIGIN`
- `X-XSS-Protection: 1; mode=block`
- `Referrer-Policy: strict-origin-when-cross-origin`
- `Content-Security-Policy` — restricts scripts, styles, images, frames, and connections to trusted origins

### Rate Limiting
- Flask-Limiter with Redis backend in production
- Global default: 200 requests/day, 50/hour
- Auth endpoints: 20/minute (5/minute for signup)
- Admin endpoints: 200/hour
- Search: 60/minute
- AI content generation: 20/hour
- Boost campaigns: 10/day
- Payments: 30 orders/hour

### Role-Based Access Control (RBAC)
- `security/rbac_service.py` implements an admin RBAC system
- Admin users are bootstrapped from environment variables
- Admin routes are protected by `@admin_required` decorators
- All admin actions are written to the audit log

### Audit Logging
- Four separate rotating log files: `app.log`, `security.log`, `audit.log`, `metrics.log`
- Security events (failed logins, account locks, password resets) are written to `security.log`
- Admin actions are written to `audit.log` by `audit_log_service.py`
- All log files rotate at 5MB with 5 backups retained

### Input Validation
- WTForms field validators on all forms
- `security/validation.py` provides additional input sanitization helpers
- SQL injection prevented by exclusive use of SQLAlchemy ORM with parameterized queries
- File upload type validation (MIME type checks) for media uploads

### Webhook Security
- Razorpay webhook signatures verified using HMAC SHA256 before any state change

---

## Performance Optimization

### Caching

Aurora uses Redis for multi-level caching:

- **Trending content cache** (`TRENDING_CACHE_TTL`, default 300s): Trending posts, reels, and hashtags are computed by background tasks and cached in Redis.
- **Explore feed cache** (`EXPLORE_CACHE_TTL`, default 300s): Explore page content is cached per user segment.
- **Recommendation cache** (`recommendation_cache.py`): Personalized recommendation results are cached with a configurable TTL.
- **AI caption cache** (`AI_CONTENT_CACHE_TTL`, default 86400s): AI-generated captions are cached for 24 hours to minimize external API calls.
- **Analytics cache** (`ANALYTICS_CACHE_TTL`, default 900s): Business analytics aggregates are cached for 15 minutes.

### Database Optimization

- PostgreSQL UUID primary keys with indexed foreign keys
- Indexes on frequently queried fields: `username`, `email`, `phone`, `created_at`
- `UniqueConstraint` and `Index` defined directly on SQLAlchemy models
- SQLAlchemy `SQLALCHEMY_TRACK_MODIFICATIONS = False` to disable overhead
- Pagination used throughout (configurable page sizes)
- Aggregated counts (follower count, following count) stored as denormalized columns on the `User` model for O(1) lookup

### Background Processing

All expensive or I/O-heavy operations are offloaded to Celery:
- Email sending
- Notification fan-out (especially to many followers)
- Media processing (video transcoding metadata extraction)
- Search index updates
- Analytics aggregation
- Interest graph computation

This keeps HTTP request latency minimal.

### Static Asset Optimization

- Nginx serves static files directly with 30-day `Cache-Control: public` headers, bypassing Flask entirely
- Static assets are stored in a named Docker volume (`staticfiles`) shared between the web and Nginx containers

### Gunicorn Concurrency

- `eventlet` worker class allows a single Gunicorn worker to handle thousands of concurrent Socket.IO connections
- Worker count scales with CPU: `(CPU × 2) + 1`

---

## Contributing

Contributions are welcome! Please follow this workflow:

### 1. Fork and Clone

```bash
git clone https://github.com/your-username/Aurora.git
cd Aurora
```

### 2. Create a Feature Branch

```bash
git checkout -b feature/your-feature-name
```

Use a descriptive branch name:
- `feature/add-stories-reactions`
- `fix/notification-duplicate-dispatch`
- `refactor/extract-media-service`

### 3. Set Up Your Development Environment

```bash
python3 -m venv venv
source venv/bin/activate
pip install -r requirements.txt
cp .env.example .env
# Edit .env: set FLASK_ENV=development, DATABASE_URL, etc.
flask db upgrade
```

### 4. Make Your Changes

- Follow PEP 8 style guidelines.
- Keep route handlers thin — business logic belongs in service files.
- Add Celery tasks for any work that is expensive or should be deferred.
- Write or update docstrings for service functions.
- Add migrations for any model changes: `flask db migrate -m "description"`.

### 5. Test Your Changes

```bash
pytest
```

Ensure no existing tests are broken. Add tests for new functionality.

### 6. Commit and Push

```bash
git add .
git commit -m "feat: add story reaction support"
git push origin feature/your-feature-name
```

### 7. Open a Pull Request

Open a pull request against `main`. Include:
- A clear description of what the PR does
- Screenshots or logs if relevant
- Reference to any related issues

### Code Style

- Use `black` for code formatting: `black app/`
- Use `flake8` for linting: `flake8 app/`
- Maximum line length: 120 characters

---

## Testing

### Running Tests

```bash
pytest
```

### Running with Coverage

```bash
pytest --cov=app --cov-report=html
```

Open `htmlcov/index.html` to view the coverage report.

### Test Configuration

The `TestingConfig` in `app/config.py` uses an in-memory SQLite database and disables CSRF protection:

```python
class TestingConfig(BaseConfig):
    TESTING = True
    WTF_CSRF_ENABLED = False
    SQLALCHEMY_DATABASE_URI = "sqlite:///:memory:"
```

Set the test database URL:

```env
TEST_DATABASE_URL=sqlite:///:memory:
```

### Running Specific Tests

```bash
pytest tests/test_auth.py
pytest tests/test_posts.py -v
pytest -k "test_login"
```

---

## Roadmap

The following improvements and expansions are planned for future releases:

### Mobile Applications
- Native iOS and Android clients consuming the Aurora REST/WebSocket API
- React Native or Flutter cross-platform app

### Infrastructure & Scalability
- Migrate to a microservices architecture (separate services for media processing, notifications, search)
- Kubernetes deployment manifests (Helm charts)
- CDN integration for media delivery (CloudFront)
- Database read replicas for analytics queries
- Horizontal auto-scaling of Celery workers

### AI & Recommendations
- Advanced collaborative filtering using user-user and item-item similarity
- ML model for content quality scoring
- AI-powered hashtag suggestions during post creation
- Sentiment analysis on comments for moderation

### Features
- Audio rooms (Twitter Spaces style)
- Polls and quizzes in stories and posts
- Collaborative posts (multi-author)
- Enhanced creator analytics dashboard with cohort analysis
- Gifting marketplace (digital gifts beyond live badges)
- Event creation and ticketing
- Multi-language localization (i18n)

### Developer Experience
- OpenAPI / Swagger documentation generated from routes
- SDK for third-party integrations
- Public developer API with API key management

---

## License

This project is licensed under the **MIT License**.

```
MIT License

Copyright (c) 2024 Aurora Contributors

Permission is hereby granted, free of charge, to any person obtaining a copy
of this software and associated documentation files (the "Software"), to deal
in the Software without restriction, including without limitation the rights
to use, copy, modify, merge, publish, distribute, sublicense, and/or sell
copies of the Software, and to permit persons to whom the Software is
furnished to do so, subject to the following conditions:

The above copyright notice and this permission notice shall be included in all
copies or substantial portions of the Software.

THE SOFTWARE IS PROVIDED "AS IS", WITHOUT WARRANTY OF ANY KIND, EXPRESS OR
IMPLIED, INCLUDING BUT NOT LIMITED TO THE WARRANTIES OF MERCHANTABILITY,
FITNESS FOR A PARTICULAR PURPOSE AND NONINFRINGEMENT. IN NO EVENT SHALL THE
AUTHORS OR COPYRIGHT HOLDERS BE LIABLE FOR ANY CLAIM, DAMAGES OR OTHER
LIABILITY, WHETHER IN AN ACTION OF CONTRACT, TORT OR OTHERWISE, ARISING FROM,
OUT OF OR IN CONNECTION WITH THE SOFTWARE OR THE USE OR OTHER DEALINGS IN THE
SOFTWARE.
```

---

## Authors

**Shah Ram** — Creator and Lead Developer
- GitHub: [@shahram8708](https://github.com/shahram8708)
- Project Repository: [https://github.com/shahram8708/Aurora](https://github.com/shahram8708/Aurora)

---

## Acknowledgements

Aurora was built on top of a rich ecosystem of open-source libraries and tools. Special thanks to the maintainers of:

- **[Flask](https://flask.palletsprojects.com/)** — The micro web framework that powers Aurora's backend
- **[Flask-SQLAlchemy](https://flask-sqlalchemy.palletsprojects.com/)** — ORM integration for Flask
- **[Flask-Migrate](https://flask-migrate.readthedocs.io/)** — Database migrations via Alembic
- **[Flask-JWT-Extended](https://flask-jwt-extended.readthedocs.io/)** — JWT authentication with cookie support
- **[Flask-SocketIO](https://flask-socketio.readthedocs.io/)** — WebSocket support for real-time features
- **[Flask-Limiter](https://flask-limiter.readthedocs.io/)** — Rate limiting
- **[Flask-WTF](https://flask-wtf.readthedocs.io/)** — CSRF protection and form handling
- **[Flask-Bcrypt](https://flask-bcrypt.readthedocs.io/)** — Password hashing
- **[Flask-Mail](https://pythonhosted.org/Flask-Mail/)** — SMTP email support
- **[Celery](https://docs.celeryq.dev/)** — Distributed task queue
- **[Redis](https://redis.io/)** — In-memory data store for caching, pub/sub, and task brokering
- **[PostgreSQL](https://www.postgresql.org/)** — Production relational database
- **[Elasticsearch](https://www.elastic.co/)** — Full-text search engine
- **[boto3](https://boto3.amazonaws.com/v1/documentation/api/latest/index.html)** — AWS SDK for Python (S3 integration)
- **[Razorpay](https://razorpay.com/docs/)** — Payment gateway
- **[Authlib](https://docs.authlib.org/)** — OAuth 2.0 client (Google login)
- **[Pillow](https://pillow.readthedocs.io/)** — Image processing
- **[MoviePy](https://zulko.github.io/moviepy/)** — Video processing
- **[hachoir](https://hachoir.readthedocs.io/)** — File metadata extraction
- **[eventlet](https://eventlet.net/)** — Async networking for Gunicorn + Socket.IO
- **[Gunicorn](https://gunicorn.org/)** — Python WSGI HTTP server
- **[Nginx](https://nginx.org/)** — High-performance reverse proxy and web server
- **[Docker](https://www.docker.com/)** — Containerization

---

## Contact

For questions, issues, feature requests, or collaboration opportunities:

- **GitHub Issues**: [https://github.com/shahram8708/Aurora/issues](https://github.com/shahram8708/Aurora/issues)
- **GitHub**: [https://github.com/shahram8708](https://github.com/shahram8708)
- **Project URL**: [https://github.com/shahram8708/Aurora](https://github.com/shahram8708/Aurora)

When reporting bugs, please include:
- Your Python version (`python --version`)
- Your operating system
- Steps to reproduce the issue
- The full error traceback from the logs
