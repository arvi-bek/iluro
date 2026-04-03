from django.shortcuts import render


class FriendlyErrorPagesMiddleware:
    """
    Force branded 404 page even while DEBUG=True.
    This keeps local/demo sessions cleaner and avoids exposing the technical 404 page.
    """

    def __init__(self, get_response):
        self.get_response = get_response

    def __call__(self, request):
        response = self.get_response(request)

        if response.status_code == 404:
            return render(request, "404.html", status=404)

        return response
