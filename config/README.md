# Configuration Guide

This directory contains configuration files for the Grocery Orchestrator connector services.

## Files

### github-codex-connector.yaml
Main configuration file for GitHub/Codex connector integration. This file defines:
- **GitHub Configuration**: API authentication, repository settings, webhooks
- **Codex Configuration**: API credentials, model settings, prompt templates
- **Connector Settings**: Logging, sync, cache, error handling, data mapping
- **Security Settings**: SSL/TLS, rate limiting, key rotation
- **Advanced Settings**: Concurrency, timeouts, debug mode

## Setup Instructions

### 1. Environment Variables
Copy the `.env.example` file to `.env` and fill in your credentials:

```bash
cp .env.example .env
```

Then edit `.env` with your actual values:
- `GITHUB_TOKEN`: Your GitHub Personal Access Token
- `CODEX_API_KEY`: Your Codex API key
- Other relevant credentials and settings

### 2. Configuration File
The `github-codex-connector.yaml` uses environment variable substitution for sensitive values (e.g., `${GITHUB_TOKEN}`).

Load the configuration in your application:

```python
import yaml

with open('config/github-codex-connector.yaml', 'r') as f:
    config = yaml.safe_load(f)
```

Or using a configuration loader that supports environment variable expansion:

```python
from dotenv import load_dotenv
import yaml
import os

load_dotenv()

with open('config/github-codex-connector.yaml', 'r') as f:
    config_text = f.read()
    # Expand environment variables in config
    config_text = os.path.expandvars(config_text)
    config = yaml.safe_load(config_text)
```

## Configuration Sections

### GitHub
- **auth**: Authentication method (PAT, OAuth, or basic auth)
- **api**: GitHub API endpoint and connection settings
- **repository**: Target repository configuration
- **webhook**: Optional webhook configuration for real-time events
- **rate_limit**: API rate limiting settings

### Codex
- **auth**: Codex API authentication credentials
- **api**: Codex API endpoint and connection settings
- **model**: Model selection and generation parameters
- **prompts**: System prompts and prompt templates

### Connector
- **logging**: Log level, file location, rotation settings
- **sync**: Automatic synchronization settings
- **cache**: Caching strategy and backend selection
- **error_handling**: Retry logic and error recovery
- **data_mapping**: Field mapping between GitHub and Codex

### Security
- **ssl_verify**: SSL/TLS certificate verification
- **ip_rate_limit**: Rate limiting by IP address
- **key_rotation**: Automatic API key rotation

## Common Tasks

### Enable Webhooks
Set `connector.webhook.enabled: true` and provide your webhook endpoint URL.

### Use Redis Cache
Change `connector.cache.backend: redis` and configure Redis connection details.

### Adjust Log Level
Change `connector.logging.level` to DEBUG, INFO, WARNING, ERROR, or CRITICAL.

### Increase API Timeouts
Modify `github.api.timeout` and `codex.api.timeout` values (in seconds).

## Security Best Practices

1. **Never commit `.env` file** to version control - add it to `.gitignore`
2. **Use strong API tokens** with minimal required permissions
3. **Rotate API keys regularly** - set `security.key_rotation.enabled: true`
4. **Enable SSL verification** in production - keep `security.ssl_verify: true`
5. **Use environment variables** for all sensitive data
6. **Restrict file permissions** on configuration files - `chmod 600 config/*`

## Troubleshooting

### Connection Issues
- Check API endpoints are correct
- Verify API tokens/keys are valid and have required permissions
- Check network connectivity and firewall rules
- Review timeout settings if requests are timing out

### Rate Limiting
- GitHub has a rate limit of 5000 requests/hour (authenticated)
- Codex may have different rate limits - check your plan
- Enable retry on rate limit: `connector.error_handling.retry_enabled: true`

### Logging
- Increase log level to DEBUG for more detailed output
- Check log files in the `logs/` directory
- Monitor application startup logs for configuration errors

## Support
For issues or questions, refer to the main repository README or contact the development team.
