from django.contrib.auth.mixins import LoginRequiredMixin

class OwnerMixin(LoginRequiredMixin):
    def get_queryset(self):
        return super().get_queryset().filter(owner=self.request.user)
