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
            content_type = response.headers.get("Content-Type", "")
            accepts_json = request.headers.get("X-Requested-With") == "XMLHttpRequest"
            if accepts_json or content_type.startswith("application/json"):
                return response
            return render(request, "404.html", status=404)

        return response
