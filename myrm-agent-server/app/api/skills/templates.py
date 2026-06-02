"""Skill instance templates (business layer).

Provides built-in templates for common skill configurations.
Uses framework's InstanceTemplate mechanism.
"""

from myrm_agent_harness.backends.skills.instance_templates import InstanceTemplate

# Built-in templates (business-specific)
BUILTIN_TEMPLATES: dict[str, list[InstanceTemplate]] = {
    "github_skill": [
        InstanceTemplate(
            template_id="github-personal",
            name="Personal Account",
            description="GitHub personal account with PAT token",
            env_overrides={
                "GITHUB_TOKEN": "<your_personal_token>",
                "GITHUB_USER": "<your_username>",
            },
            config_overrides={},
        ),
        InstanceTemplate(
            template_id="github-work",
            name="Work Account",
            description="GitHub work/organization account",
            env_overrides={
                "GITHUB_TOKEN": "<your_work_token>",
                "GITHUB_ORG": "<your_org>",
            },
            config_overrides={},
        ),
    ],
    "mysql_skill": [
        InstanceTemplate(
            template_id="mysql-prod",
            name="Production Database",
            description="Production MySQL connection",
            env_overrides={
                "MYSQL_HOST": "prod.mysql.example.com",
                "MYSQL_USER": "<username>",
                "MYSQL_PASSWORD": "<password>",
                "MYSQL_DATABASE": "prod_db",
            },
            config_overrides={"port": 3306, "timeout": 30},
        ),
        InstanceTemplate(
            template_id="mysql-dev",
            name="Development Database",
            description="Development MySQL connection",
            env_overrides={
                "MYSQL_HOST": "localhost",
                "MYSQL_USER": "root",
                "MYSQL_PASSWORD": "dev_password",
                "MYSQL_DATABASE": "dev_db",
            },
            config_overrides={"port": 3306, "timeout": 10},
        ),
    ],
}


def get_templates_for_skill(skill_name: str) -> list[InstanceTemplate]:
    """Get all templates for a skill.

    Args:
        skill_name: Skill name (e.g., "github_skill")

    Returns:
        List of templates (empty if no templates available)
    """
    return BUILTIN_TEMPLATES.get(skill_name, [])


def get_template(skill_name: str, template_id: str) -> InstanceTemplate | None:
    """Get a specific template.

    Args:
        skill_name: Skill name
        template_id: Template ID

    Returns:
        Template if found, None otherwise
    """
    templates = get_templates_for_skill(skill_name)
    return next((t for t in templates if t.template_id == template_id), None)
