from .models import CompanyConfig


def company_config(request):
    return {"company": CompanyConfig.get_or_default()}
