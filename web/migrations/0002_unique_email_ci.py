from django.db import migrations

class Migration(migrations.Migration):

    dependencies = [
        ('web', '0001_initial'),  # sửa theo migration cuối của app web
    ]

    operations = [
        migrations.RunSQL(
            sql="""
                CREATE UNIQUE INDEX IF NOT EXISTS auth_user_email_ci_uq
                ON auth_user (LOWER(email));
            """,
            reverse_sql="""
                DROP INDEX IF EXISTS auth_user_email_ci_uq;
            """,
        ),
    ]
