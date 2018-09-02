class SnippetCollection:
    def __init__(self, url, snippet=None):
        self.URL = url
        if snippet == None:
            self.snippets = []
        else:
            self.snippets = [snippet, ]
