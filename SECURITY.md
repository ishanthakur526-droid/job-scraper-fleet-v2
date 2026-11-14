# Security

## Reporting a problem

Please report security issues privately through GitHub: **Security → Report a vulnerability** on this repository (a private advisory). Do not open a public issue for them. You should get a reply within a week.

## How JobFleet handles risk

- **No credentials in the project.** Claude features use the Claude Code CLI's own login; optional search API keys (`SERPAPI_KEY`, `BRAVE_SEARCH_API_KEY`) are read from environment variables only and redacted from logs and error messages.
- **Job postings are untrusted input.** They are parsed as data and never executed. The daily Claude review runs with all tools disabled and is told to ignore instructions inside job text; the weekly company scout may only search and read web pages, and every address it suggests is verified by ordinary code before use.
- **The dashboard escapes all job text** before displaying it, and embeds data so that it cannot close the page's script.
- **Cloud mode** uses GitHub's built-in token with the minimum permissions per workflow; form values reach scripts as environment variables, not as code.
- CI runs the test suite and a [gitleaks](https://github.com/gitleaks/gitleaks) secret scan on every push and pull request.
