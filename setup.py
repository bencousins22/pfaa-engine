from setuptools import setup, find_packages

setup(
    name="agent_setup_cli",
    version="0.1.0",
    packages=find_packages(),
    install_requires=[
        "typer>=0.9.0",
        "sqlalchemy>=2.0.0",
        "pydantic>=2.0.0",
        "alembic>=1.12.0",
        "rich>=13.0.0",
        "fastapi>=0.70.0",
        "uvicorn[standard]>=0.15.0",
        "websockets>=10.0.0",
        "anthropic>=0.18.0",
        "pyyaml>=6.0.0",
        "cryptography>=41.0.0"
    ],
    entry_points={
        "console_scripts": [
            "agent-setup=agent_setup_cli.cli.__main__:app",
        ],
    },
)
