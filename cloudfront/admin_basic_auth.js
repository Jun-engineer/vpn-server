function handler(event) {
    var request = event.request;
    var uri = request.uri;

    if (uri === "/admin.html") {
        var headers = request.headers;
        var authHeader = headers.authorization ? headers.authorization.value : "";
        var expected = "${basic_header}";

        if (authHeader !== expected) {
            return {
                statusCode: 401,
                statusDescription: "Unauthorized",
                headers: {
                    "www-authenticate": { value: "Basic realm=\"VPN Admin\"" },
                    "cache-control": { value: "no-store" },
                    "content-type": { value: "text/plain" }
                },
                body: "Authentication required"
            };
        }
    }

    return request;
}
