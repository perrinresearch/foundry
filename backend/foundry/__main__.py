"""Run: python -m foundry"""

from __future__ import annotations

import uvicorn

from foundry.config import settings


def main() -> None:
    uvicorn.run(
        "foundry.api.app:app",
        host=settings.listen_host,
        port=settings.listen_port,
        reload=False,
        proxy_headers=True,
        forwarded_allow_ips="*",
    )


if __name__ == "__main__":
    main()
