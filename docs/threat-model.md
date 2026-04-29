# Threat Model

## Assets and Threats

| Asset | Threat | Likelihood | Impact | Mitigation |
|---|---|---|---|---|
| Build system | Malicious repo triggers RCE on host | Medium | Critical | Container sandboxing, no privileged mode, resource limits |
| API | Unauthenticated deployment trigger | High | High | Bearer token auth on all endpoints |
| Webhook endpoint | Forged GitHub push events | High | High | HMAC-SHA256 signature verification |
| Dashboard | Unauthorized access to service management | High | High | Auth required, no public endpoints |
| Build logs | Log injection / XSS via malicious repo output | Medium | Medium | Sanitize log output before rendering in React |
| Docker socket | Direct access bypasses all auth | Low | Critical | Socket only accessible by backend process |
| PostgreSQL | Direct database access | Low | High | DB not exposed outside VM, strong password |
| Container network | Cross-container communication | Low | Medium | Containers on isolated networks by default |

## Trust Boundaries

1. **External → Nginx:** Untrusted. All traffic enters here.
2. **Nginx → FastAPI:** Semi-trusted. Nginx forwards real IP.
3. **FastAPI → Docker:** Trusted. Internal only.
4. **FastAPI → PostgreSQL:** Trusted. Internal only.
5. **Container → Host:** Untrusted. Containers treated as hostile.
