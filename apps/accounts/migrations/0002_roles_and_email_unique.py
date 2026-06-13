"""Two structural fixes that the default User model can't express on its own:

1. Create the ``seeker`` and ``facilitator`` groups that RBAC keys off of.
2. Add a case-insensitive UNIQUE index on auth_user.email. Django's default User
   does not enforce email uniqueness; this closes that gap at the database level
   (the strongest guarantee) without swapping the User model, which the spec forbids.
"""

from django.db import migrations

ROLES = ["seeker", "facilitator"]


def create_groups(apps, schema_editor):
    Group = apps.get_model("auth", "Group")
    for name in ROLES:
        Group.objects.get_or_create(name=name)


def delete_groups(apps, schema_editor):
    Group = apps.get_model("auth", "Group")
    Group.objects.filter(name__in=ROLES).delete()


class Migration(migrations.Migration):
    dependencies = [
        ("accounts", "0001_initial"),
        ("auth", "0012_alter_user_first_name_max_length"),
    ]

    operations = [
        migrations.RunPython(create_groups, delete_groups),
        migrations.RunSQL(
            sql=(
                "CREATE UNIQUE INDEX uniq_auth_user_email_ci "
                "ON auth_user (LOWER(email)) WHERE email <> '';"
            ),
            reverse_sql="DROP INDEX IF EXISTS uniq_auth_user_email_ci;",
        ),
    ]
