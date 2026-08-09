"""Site configuration — every operator-editable value shown on the public pages.

The bank's vPOS certification checks these values on the live site (legal name,
contacts, address), so they come from env vars (``WEB_*``) and must be set to the
real registered values before the site is submitted for certification. Defaults
keep local dev working; see the root ``.env.example`` and docs/GO_LIVE_GUIDE.md.
"""

import os

from pydantic import BaseModel


class SiteConfig(BaseModel):
    """Values rendered into the public pages (footer, contacts, legal pages)."""

    company_legal_name: str = "DeepClare"
    company_unn: str = ""
    company_address: str = ""
    contact_email: str = "contact@deepclare.am"
    contact_phone: str = ""
    telegram_link: str = ""
    base_url: str = "http://localhost:8090"
    # Current Chrome Web Store listing; override via WEB_CHROME_STORE_URL when it changes.
    chrome_store_url: str = (
        "https://chromewebstore.google.com/detail/deepclare/pnnmdcbccmkjnedalijbfoclakemmehe"
    )

    @classmethod
    def from_env(cls) -> "SiteConfig":
        # "changeme" is the .env.example placeholder — never let it reach a page.
        overrides = {
            name: value
            for name in cls.model_fields
            if (value := os.environ.get(f"WEB_{name.upper()}")) and value != "changeme"
        }
        return cls(**overrides)
