def get_smile(text: str):
    return text.encode('utf-16', 'surrogatepass').decode('utf-16')
