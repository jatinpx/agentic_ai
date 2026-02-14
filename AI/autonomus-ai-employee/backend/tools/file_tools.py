def save_to_file(text: str):
    with open("output.txt", 'a') as f:
        f.write(text + "\n")
    return "saved to file"

