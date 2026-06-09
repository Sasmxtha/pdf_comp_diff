import fitz

for label, path in [("OLD", r"C:\Users\nithe\OneDrive\Desktop\pdf\old.pdf"),
                    ("NEW", r"C:\Users\nithe\OneDrive\Desktop\pdf\new.pdf")]:
    doc = fitz.open(path)
    print(f"\n{'='*60}\n{label} PDF  ({len(doc)} pages)\n{'='*60}")
    for i, page in enumerate(doc):
        txt = page.get_text()
        print(f"\n--- Page {i+1} ---\n{txt[:1000]}")
    doc.close()
