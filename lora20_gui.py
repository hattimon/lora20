import tkinter as tk
from tkinter import messagebox
import json
from pathlib import Path
import re

try:
    from appdirs import user_data_dir  # pip install appdirs
except ImportError:
    user_data_dir = None

try:
    import cbor2  # pip install cbor2
except ImportError:
    cbor2 = None


APP_NAME = "lora20_gui"
APP_AUTHOR = "lora20"

DEFAULT_SETTINGS = {
    "theme": "dark",   # dark / light
    "language": "pl",  # en / pl
}

MAX_PAYLOAD = 51  # bytes
FRAG_HEADER_SIZE = 4  # 2B msg_id + 1B idx + 1B total


# ---------- DC cost ----------

def calc_dc_cost(length: int) -> int:
    if length <= 0:
        return 0
    return (length + 23) // 24  # każde rozpoczęte 24B = 1 DC


# ---------- SETTINGS ----------

def get_settings_path() -> Path:
    if user_data_dir is not None:
        base = Path(user_data_dir(APP_NAME, APP_AUTHOR))
    else:
        base = Path.home() / f".{APP_NAME}"
    base.mkdir(parents=True, exist_ok=True)
    return base / "settings.json"


def load_settings():
    path = get_settings_path()
    if not path.exists():
        return DEFAULT_SETTINGS.copy()
    try:
        with open(path, "r", encoding="utf-8") as f:
            data = json.load(f)
        for k, v in DEFAULT_SETTINGS.items():
            data.setdefault(k, v)
        return data
    except Exception:
        return DEFAULT_SETTINGS.copy()


def save_settings(settings):
    path = get_settings_path()
    try:
        with open(path, "w", encoding="utf-8") as f:
            json.dump(settings, f, ensure_ascii=False, indent=2)
    except Exception as e:
        print("Failed to save settings:", e)


# ---------- FRAGMENTATION ----------

def fragment_cbor(cbor_bytes: bytes, max_payload: int = MAX_PAYLOAD,
                  msg_id: int = 1):
    """
    Zwraca listę fragmentów: każdy to bytes:
    [msg_id_hi, msg_id_lo, frag_idx, frag_cnt] + cbor_slice
    """
    if max_payload <= FRAG_HEADER_SIZE:
        raise ValueError("max_payload too small for header")

    frag_data_len = max_payload - FRAG_HEADER_SIZE
    total_len = len(cbor_bytes)
    frag_cnt = (total_len + frag_data_len - 1) // frag_data_len

    frags = []
    msg_hi = (msg_id >> 8) & 0xFF
    msg_lo = msg_id & 0xFF

    for idx in range(frag_cnt):
        start = idx * frag_data_len
        end = start + frag_data_len
        chunk = cbor_bytes[start:end]
        header = bytes([msg_hi, msg_lo, idx, frag_cnt])
        frags.append(header + chunk)
    return frags


def reassemble_fragments(frag_list):
    """
    frag_list: lista bytes z nagłówkiem 4B.
    Zwraca pełne cbor_bytes (bez nagłówków).
    Nie robi walidacji brakujących fragmentów – to demo.
    """
    if not frag_list:
        return b""
    sorted_frags = sorted(frag_list, key=lambda b: b[2])
    parts = [f[FRAG_HEADER_SIZE:] for f in sorted_frags]
    return b"".join(parts)


# ---------- GUI ----------

class Lora20GUI(tk.Tk):
    def __init__(self):
        super().__init__()
        self.settings = load_settings()

        self.title("lora20 encoder / decoder (CBOR)")

        self.style_colors = {}
        self.texts = {}
        self._init_translations()
        self._apply_theme_colors()
        self._build_menu()
        self._build_banner()
        self._build_layout()
        self._apply_theme_to_widgets()

        # dopasuj okno do treści tak, żeby wszystko było widoczne
        self.update_idletasks()
        width = self.winfo_reqwidth()
        height = self.winfo_reqheight()
        self.geometry(f"{width}x{height}")

    # ----- translations -----

    def _init_translations(self):
        explanation_pl = """Protokół lora20 opisuje operacje na tokenach w postaci JSON.

Przykład deploy – utworzenie nowego tokena:
  {"p":"lora20","op":"deploy","tick":"TOKEN","max":"21000000","lim":"1000"}

Mint:
  {"p":"lora20","op":"mint","tick":"TOKEN","amt":"1000"}

Transfer:
  {"p":"lora20","op":"transfer","tick":"TOKEN","amt":"50","to":"Odbiorca"}

Link:
  {"p":"lora20","op":"link","addr":"AdresPortfela"}

Aplikacja buduje JSON z formularza i koduje go do CBOR (binarne kodowanie JSON).

Kodowanie CBOR:
  JSON → obiekt Pythona → CBOR (bajty) → hex.

Dekodowanie CBOR:
  hex → bajty → obiekt → JSON (tekst).

Każda wartość (tick, max, lim, amt, to, addr) jest zachowana 1:1 logicznie,
a payload CBOR jest zwykle krótszy niż tekstowy JSON.

Fragmentacja:
  Jeśli CBOR > limitu 51 bajtów, aplikacja dzieli go na kilka fragmentów.
  Każdy fragment ma nagłówek:
    msg_id (2B), frag_idx (1B), frag_cnt (1B) + dane CBOR.
  Po stronie serwera można odebrane fragmenty złożyć w kolejności
  frag_idx i dekodować CBOR do oryginalnego JSON.

Koszt: każde rozpoczęte 24 bajty payloadu = 1 DC w sieci Helium.
"""

        explanation_en = """The lora20 protocol describes token operations as JSON.

Example deploy – create a new token:
  {"p":"lora20","op":"deploy","tick":"TOKEN","max":"21000000","lim":"1000"}

Mint:
  {"p":"lora20","op":"mint","tick":"TOKEN","amt":"1000"}

Transfer:
  {"p":"lora20","op":"transfer","tick":"TOKEN","amt":"50","to":"Recipient"}

Link:
  {"p":"lora20","op":"link","addr":"WalletAddress"}

The app builds JSON from the form and encodes it as CBOR (binary JSON).

CBOR encoding:
  JSON → Python object → CBOR bytes → hex.

CBOR decoding:
  hex → bytes → object → JSON string.

All values (tick, max, lim, amt, to, addr) are preserved logically 1:1,
with CBOR payload usually shorter than plain JSON text.

Fragmentation:
  If CBOR > 51 bytes, the app splits it into several fragments.
  Each fragment header:
    msg_id (2B), frag_idx (1B), frag_cnt (1B) + CBOR data.
  On the server side you can reorder by frag_idx, concatenate the data
  and decode CBOR back to the original JSON.

Cost: each started 24 bytes of payload = 1 DC on Helium.
"""

        self.texts = {
            "pl": {
                "builder_frame": "🧩 Kreator operacji (JSON lora20)",
                "builder_op": "Operacja",
                "builder_tick": "Ticker (1–8 znaków A-Z0-9)",
                "builder_max": "Max supply (max, cyfry, ≤8)",
                "builder_lim": "Limit mintu na operację (lim, cyfry, ≤8)",
                "builder_amt": "Ilość (amt, cyfry, ≤8)",
                "builder_to": "Odbiorca (to)",
                "builder_addr": "Adres portfela (addr, np. Solana)",
                "builder_build": "Zbuduj JSON z formularza",
                "cbor_frame": "📦 JSON ↔ CBOR (uplink)",
                "encode_cbor_btn": "Koduj JSON → CBOR hex",
                "decode_cbor_btn": "Dekoduj CBOR hex → JSON",
                "frag_frame": "✂️ Fragmentacja CBOR na wiele ramek",
                "build_frags_btn": "Zbuduj fragmenty z obecnego CBOR",
                "expl_frame": "ℹ️ Wyjaśnienie protokołu lora20, CBOR i fragmentacji",
                "limit_label": (
                    "📏 Limit payloadu: 51 bajtów. "
                    "Jeśli len > limit, aplikacja może podzielić wiadomość na kilka ramek."
                ),
                "default_json":
                    '{"p":"lora20","op":"mint","tick":"LORA","amt":"100"}',
                "explanation": explanation_pl,
                "menu_view": "Widok",
                "menu_theme_dark": "Motyw ciemny",
                "menu_theme_light": "Motyw jasny",
                "menu_lang": "Język",
                "menu_lang_en": "Angielski",
                "menu_lang_pl": "Polski",
                "menu_help": "Pomoc",
                "menu_help_open": "Otwórz okno z wyjaśnieniem",
            },
            "en": {
                "builder_frame": "🧩 Operation builder (lora20 JSON)",
                "builder_op": "Operation",
                "builder_tick": "Tick (1–8 chars A-Z0-9)",
                "builder_max": "Max supply (max, digits, ≤8)",
                "builder_lim": "Mint limit per operation (lim, digits, ≤8)",
                "builder_amt": "Amount (amt, digits, ≤8)",
                "builder_to": "Recipient (to)",
                "builder_addr": "Wallet address (addr, e.g. Solana)",
                "builder_build": "Build JSON from form",
                "cbor_frame": "📦 JSON ↔ CBOR (uplink)",
                "encode_cbor_btn": "Encode JSON → CBOR hex",
                "decode_cbor_btn": "Decode CBOR hex → JSON",
                "frag_frame": "✂️ CBOR fragmentation into multiple frames",
                "build_frags_btn": "Build fragments from current CBOR",
                "expl_frame": "ℹ️ lora20 protocol, CBOR & fragmentation",
                "limit_label": (
                    "📏 Payload limit: 51 bytes. "
                    "If len > limit, the app can split the message into multiple frames."
                ),
                "default_json":
                    '{"p":"lora20","op":"mint","tick":"LORA","amt":"100"}',
                "explanation": explanation_en,
                "menu_view": "View",
                "menu_theme_dark": "Dark theme",
                "menu_theme_light": "Light theme",
                "menu_lang": "Language",
                "menu_lang_en": "English",
                "menu_lang_pl": "Polish",
                "menu_help": "Help",
                "menu_help_open": "Open explanation window",
            },
        }

    # ----- theme -----

    def _apply_theme_colors(self):
        if self.settings.get("theme") == "dark":
            self.style_colors = {
                "bg": "#000000",
                "fg": "#FFFFFF",
                "frame_bg": "#000000",
                "entry_bg": "#202020",
                "entry_fg": "#FFFFFF",
                "entry_disabled_bg": "#303030",
                "entry_disabled_fg": "#888888",
            }
        else:
            self.style_colors = {
                "bg": "#f3f4f6",
                "fg": "#111827",
                "frame_bg": "#ffffff",
                "entry_bg": "#ffffff",
                "entry_fg": "#111827",
                "entry_disabled_bg": "#e5e7eb",
                "entry_disabled_fg": "#9ca3af",
            }
        self.configure(bg=self.style_colors["bg"])

    def _apply_theme_to_widgets(self):
        def apply(widget):
            if isinstance(widget, tk.LabelFrame):
                widget.configure(
                    bg=self.style_colors["frame_bg"],
                    fg=self.style_colors["fg"],
                )
            elif isinstance(widget, tk.Frame):
                widget.configure(bg=self.style_colors["frame_bg"])
            elif isinstance(widget, tk.Label):
                widget.configure(
                    bg=self.style_colors["frame_bg"],
                    fg=self.style_colors["fg"],
                )
            elif isinstance(widget, tk.Text):
                state = widget.cget("state")
                if state == "disabled":
                    widget.configure(
                        bg=self.style_colors["entry_disabled_bg"],
                        fg=self.style_colors["entry_disabled_fg"],
                        insertbackground=self.style_colors["fg"],
                    )
                else:
                    widget.configure(
                        bg=self.style_colors["entry_bg"],
                        fg=self.style_colors["entry_fg"],
                        insertbackground=self.style_colors["fg"],
                    )
            elif isinstance(widget, tk.Entry):
                state = widget.cget("state")
                if state == "disabled":
                    widget.configure(
                        disabledbackground=self.style_colors["entry_disabled_bg"],
                        disabledforeground=self.style_colors["entry_disabled_fg"],
                        readonlybackground=self.style_colors["entry_disabled_bg"],
                    )
                else:
                    widget.configure(
                        bg=self.style_colors["entry_bg"],
                        fg=self.style_colors["entry_fg"],
                        insertbackground=self.style_colors["fg"],
                    )
            elif isinstance(widget, tk.Button):
                widget.configure(
                    bg=self.style_colors["entry_bg"],
                    fg=self.style_colors["entry_fg"],
                    activebackground="#444444",
                    activeforeground=self.style_colors["fg"],
                )
            for child in widget.winfo_children():
                apply(child)

        apply(self)

    # ----- menu -----

    def _build_menu(self):
        t = self.texts[self.settings["language"]]
        menubar = tk.Menu(self)

        view_menu = tk.Menu(menubar, tearoff=0)
        view_menu.add_command(
            label=t["menu_theme_dark"],
            command=lambda: self._set_theme("dark"),
        )
        view_menu.add_command(
            label=t["menu_theme_light"],
            command=lambda: self._set_theme("light"),
        )
        menubar.add_cascade(label=t["menu_view"], menu=view_menu)

        lang_menu = tk.Menu(menubar, tearoff=0)
        lang_menu.add_command(
            label=t["menu_lang_en"],
            command=lambda: self._set_language("en"),
        )
        lang_menu.add_command(
            label=t["menu_lang_pl"],
            command=lambda: self._set_language("pl"),
        )
        menubar.add_cascade(label=t["menu_lang"], menu=lang_menu)

        help_menu = tk.Menu(menubar, tearoff=0)
        help_menu.add_command(
            label=t["menu_help_open"],
            command=self._open_help_window,
        )
        menubar.add_cascade(label=t["menu_help"], menu=help_menu)

        self.config(menu=menubar)

    def _set_theme(self, theme: str):
        self.settings["theme"] = theme
        save_settings(self.settings)
        self._apply_theme_colors()
        self._apply_theme_to_widgets()

    def _set_language(self, lang: str):
        self.settings["language"] = lang
        save_settings(self.settings)
        # przebuduj menu, napisy i tytuł okna
        self._build_menu()
        self._relabel_widgets()
        self.title("lora20 encoder / decoder (CBOR)")

    # ----- banner -----

    def _build_banner(self):
        banner = tk.Frame(self, bg=self.style_colors["bg"])
        banner.pack(fill="x")
        title = tk.Label(
            banner,
            text="lora20 encoder / decoder (CBOR)",
            bg=self.style_colors["bg"],
            fg=self.style_colors["fg"],
            font=("Segoe UI", 12, "bold"),
        )
        title.pack(anchor="w", padx=10, pady=5)

    # ----- layout -----

    def _build_layout(self):
        t = self.texts[self.settings["language"]]

        main = tk.Frame(self, bg=self.style_colors["frame_bg"])
        main.pack(fill="both", expand=True)

        left = tk.Frame(main, bg=self.style_colors["frame_bg"])
        right = tk.Frame(main, bg=self.style_colors["frame_bg"])
        left.pack(side="left", fill="both", expand=False, padx=5, pady=5)
        right.pack(side="right", fill="both", expand=False, padx=5, pady=5)

        # --- builder ---

        self.builder_frame = tk.LabelFrame(left, text=t["builder_frame"])
        self.builder_frame.pack(fill="x", padx=5, pady=5)

        row = 0
        self.lbl_builder_op = tk.Label(self.builder_frame, text=t["builder_op"])
        self.lbl_builder_op.grid(row=row, column=0, padx=5, pady=2, sticky="w")
        self.op_var = tk.StringVar(value="mint")
        self.op_menu = tk.OptionMenu(
            self.builder_frame,
            self.op_var,
            "deploy",
            "mint",
            "transfer",
            "link",
            command=self._on_op_change,
        )
        self.op_menu.grid(row=row, column=1, padx=5, pady=2, sticky="w")

        row += 1
        self.lbl_builder_tick = tk.Label(self.builder_frame, text=t["builder_tick"])
        self.lbl_builder_tick.grid(row=row, column=0, padx=5, pady=2, sticky="w")
        self.tick_entry = tk.Entry(self.builder_frame, width=20)
        self.tick_entry.grid(row=row, column=1, padx=5, pady=2, sticky="w")
        self.tick_entry.insert(0, "LORA")

        row += 1
        self.lbl_builder_max = tk.Label(self.builder_frame, text=t["builder_max"])
        self.lbl_builder_max.grid(row=row, column=0, padx=5, pady=2, sticky="w")
        self.max_entry = tk.Entry(self.builder_frame, width=20)
        self.max_entry.grid(row=row, column=1, padx=5, pady=2, sticky="w")
        self.max_entry.insert(0, "21000000")

        row += 1
        self.lbl_builder_lim = tk.Label(self.builder_frame, text=t["builder_lim"])
        self.lbl_builder_lim.grid(row=row, column=0, padx=5, pady=2, sticky="w")
        self.lim_entry = tk.Entry(self.builder_frame, width=20)
        self.lim_entry.grid(row=row, column=1, padx=5, pady=2, sticky="w")
        self.lim_entry.insert(0, "1000")

        row += 1
        self.lbl_builder_amt = tk.Label(self.builder_frame, text=t["builder_amt"])
        self.lbl_builder_amt.grid(row=row, column=0, padx=5, pady=2, sticky="w")
        self.amt_entry = tk.Entry(self.builder_frame, width=20)
        self.amt_entry.grid(row=row, column=1, padx=5, pady=2, sticky="w")
        self.amt_entry.insert(0, "100")

        row += 1
        self.lbl_builder_to = tk.Label(self.builder_frame, text=t["builder_to"])
        self.lbl_builder_to.grid(row=row, column=0, padx=5, pady=2, sticky="w")
        self.to_entry = tk.Entry(self.builder_frame, width=40)
        self.to_entry.grid(row=row, column=1, padx=5, pady=2, sticky="w")

        row += 1
        self.lbl_builder_addr = tk.Label(self.builder_frame, text=t["builder_addr"])
        self.lbl_builder_addr.grid(row=row, column=0, padx=5, pady=2, sticky="w")
        self.addr_entry = tk.Entry(self.builder_frame, width=60)
        self.addr_entry.grid(row=row, column=1, padx=5, pady=2, sticky="w")
        self.addr_entry.insert(0, "Adres portfela (np. Solana)")

        row += 1
        self.build_btn = tk.Button(
            self.builder_frame,
            text=t["builder_build"],
            command=self.build_json_from_form,
        )
        self.build_btn.grid(row=row, column=0, columnspan=2,
                            padx=5, pady=5, sticky="w")

        # --- JSON tekst (podgląd) ---

        self.json_text = tk.Text(left, height=4, wrap="word")
        self.json_text.pack(fill="x", padx=5, pady=5)
        self.json_text.insert("1.0", t["default_json"])

        # --- CBOR sekcja ---

        self.cbor_frame = tk.LabelFrame(left, text=t["cbor_frame"])
        self.cbor_frame.pack(fill="x", padx=5, pady=5)

        self.cbor_encode_btn = tk.Button(
            self.cbor_frame, text=t["encode_cbor_btn"], command=self.encode_cbor
        )
        self.cbor_encode_btn.grid(row=0, column=0, padx=5, pady=5, sticky="w")

        self.cbor_decode_btn = tk.Button(
            self.cbor_frame, text=t["decode_cbor_btn"], command=self.decode_cbor
        )
        self.cbor_decode_btn.grid(row=0, column=1, padx=5, pady=5, sticky="w")

        self.cbor_bytes_label = tk.Label(self.cbor_frame, text="📦 CBOR bytes: 0")
        self.cbor_bytes_label.grid(row=1, column=0, padx=5, pady=2, sticky="w")

        self.cbor_dc_label = tk.Label(self.cbor_frame, text="💸 DC cost: 0")
        self.cbor_dc_label.grid(row=1, column=1, padx=5, pady=2, sticky="w")

        tk.Label(self.cbor_frame, text="HEX (CBOR):").grid(
            row=2, column=0, padx=5, pady=2, sticky="w"
        )
        self.cbor_hex_entry = tk.Entry(self.cbor_frame, width=40)
        self.cbor_hex_entry.grid(row=2, column=1, padx=5, pady=2, sticky="we")
        self.cbor_frame.columnconfigure(1, weight=1)

        self.cbor_decoded_text = tk.Text(self.cbor_frame, height=4, wrap="word")
        self.cbor_decoded_text.grid(
            row=3, column=0, columnspan=2, padx=5, pady=5, sticky="we"
        )

        # --- fragmentacja ---

        self.frag_frame = tk.LabelFrame(left, text=t["frag_frame"])
        self.frag_frame.pack(fill="x", padx=5, pady=5)

        self.build_frags_btn = tk.Button(
            self.frag_frame, text=t["build_frags_btn"], command=self.build_fragments
        )
        self.build_frags_btn.pack(pady=5, anchor="w", padx=5)

        self.frag_info_label = tk.Label(self.frag_frame, text="Brak fragmentów.")
        self.frag_info_label.pack(anchor="w", padx=5)

        self.frag_text = tk.Text(self.frag_frame, height=5, wrap="word")
        self.frag_text.pack(fill="x", padx=5, pady=5)

        # --- prawa kolumna ---

        self.expl_frame = tk.LabelFrame(right, text=t["expl_frame"])
        self.expl_frame.pack(fill="both", expand=True, padx=5, pady=5)

        self.expl_text = tk.Text(self.expl_frame, wrap="word", height=20)
        self.expl_scroll = tk.Scrollbar(
            self.expl_frame, command=self.expl_text.yview
        )
        self.expl_text.configure(yscrollcommand=self.expl_scroll.set)
        self.expl_text.pack(side="left", fill="both",
                            expand=True, padx=5, pady=5)
        self.expl_scroll.pack(side="right", fill="y")
        self.expl_text.insert("1.0", t["explanation"])
        self.expl_text.config(state="disabled")

        self.limit_label = tk.Label(
            right, text=t["limit_label"], justify="left", anchor="w", wraplength=260
        )
        self.limit_label.pack(fill="x", padx=5, pady=(0, 5))

        self._on_op_change(self.op_var.get())

    # ----- relabel -----

    def _relabel_widgets(self):
        t = self.texts[self.settings["language"]]

        # ramki
        self.builder_frame.config(text=t["builder_frame"])
        self.cbor_frame.config(text=t["cbor_frame"])
        self.frag_frame.config(text=t["frag_frame"])
        self.expl_frame.config(text=t["expl_frame"])

        # etykiety w builderze
        self.lbl_builder_op.config(text=t["builder_op"])
        self.lbl_builder_tick.config(text=t["builder_tick"])
        self.lbl_builder_max.config(text=t["builder_max"])
        self.lbl_builder_lim.config(text=t["builder_lim"])
        self.lbl_builder_amt.config(text=t["builder_amt"])
        self.lbl_builder_to.config(text=t["builder_to"])
        self.lbl_builder_addr.config(text=t["builder_addr"])

        # przyciski
        self.build_btn.config(text=t["builder_build"])
        self.cbor_encode_btn.config(text=t["encode_cbor_btn"])
        self.cbor_decode_btn.config(text=t["decode_cbor_btn"])
        self.build_frags_btn.config(text=t["build_frags_btn"])

        # labelki w sekcji CBOR (reset wartości)
        self.cbor_bytes_label.config(text="📦 CBOR bytes: 0")
        self.cbor_dc_label.config(text="💸 DC cost: 0")

        # limit
        self.limit_label.config(text=t["limit_label"])

        # wyjaśnienie
        self.expl_text.config(state="normal")
        self.expl_text.delete("1.0", "end")
        self.expl_text.insert("1.0", t["explanation"])
        self.expl_text.config(state="disabled")

        # domyślny JSON tylko gdy pole jest puste
        if not self.json_text.get("1.0", "end").strip():
            self.json_text.insert("1.0", t["default_json"])

        self._apply_theme_to_widgets()

    # ----- help window -----

    def _open_help_window(self):
        t = self.texts[self.settings["language"]]
        win = tk.Toplevel(self)
        win.title("lora20 help")
        win.geometry("600x400")
        txt = tk.Text(win, wrap="word")
        scr = tk.Scrollbar(win, command=txt.yview)
        txt.configure(yscrollcommand=scr.set)
        txt.pack(side="left", fill="both", expand=True)
        scr.pack(side="right", fill="y")
        txt.insert("1.0", t["explanation"])
        txt.config(state="disabled")
        self._apply_theme_to_widgets()

    # ----- validation -----

    def _validate_tick(self, tick: str) -> str:
        tick = tick.strip().upper()
        if not (1 <= len(tick) <= 8):
            raise ValueError("tick musi mieć 1–8 znaków")
        if not re.fullmatch(r"[A-Z0-9]+", tick):
            raise ValueError("tick może zawierać tylko A-Z i 0-9")
        return tick

    def _validate_number_field(self, value: str, name: str) -> str:
        value = value.strip()
        if value == "":
            raise ValueError(f"{name} nie może być puste")
        if not re.fullmatch(r"[0-9]+", value):
            raise ValueError(f"{name} może zawierać tylko cyfry 0-9")
        if len(value) > 8:
            raise ValueError(f"{name} może mieć maksymalnie 8 cyfr")
        return value

    # ----- builder behaviour -----

    def _on_op_change(self, op: str):
        if op == "deploy":
            self._set_entry_state(self.max_entry, True)
            self._set_entry_state(self.lim_entry, True)
            self._set_entry_state(self.amt_entry, False)
            self._set_entry_state(self.to_entry, False)
            self._set_entry_state(self.addr_entry, False)
        elif op == "mint":
            self._set_entry_state(self.max_entry, False)
            self._set_entry_state(self.lim_entry, False)
            self._set_entry_state(self.amt_entry, True)
            self._set_entry_state(self.to_entry, False)
            self._set_entry_state(self.addr_entry, False)
        elif op == "transfer":
            self._set_entry_state(self.max_entry, False)
            self._set_entry_state(self.lim_entry, False)
            self._set_entry_state(self.amt_entry, True)
            self._set_entry_state(self.to_entry, True)
            self._set_entry_state(self.addr_entry, False)
        elif op == "link":
            self._set_entry_state(self.max_entry, False)
            self._set_entry_state(self.lim_entry, False)
            self._set_entry_state(self.amt_entry, False)
            self._set_entry_state(self.to_entry, False)
            self._set_entry_state(self.addr_entry, True)
        self._apply_theme_to_widgets()

    def _set_entry_state(self, entry: tk.Entry, enabled: bool):
        if enabled:
            entry.configure(state="normal")
        else:
            entry.configure(state="disabled")

    def _build_json_from_form_internal(self):
        op = self.op_var.get()
        tick_raw = self.tick_entry.get()
        max_raw = self.max_entry.get()
        lim_raw = self.lim_entry.get()
        amt_raw = self.amt_entry.get()
        to_str = self.to_entry.get().strip()
        addr_str = self.addr_entry.get().strip()

        result = {"p": "lora20", "op": op}

        if op in ("deploy", "mint", "transfer"):
            tick = self._validate_tick(tick_raw)
            result["tick"] = tick

        if op == "deploy":
            max_val = self._validate_number_field(max_raw, "max")
            lim_val = self._validate_number_field(lim_raw, "lim")
            result["max"] = max_val
            result["lim"] = lim_val
        elif op == "mint":
            amt_val = self._validate_number_field(amt_raw, "amt")
            result["amt"] = amt_val
        elif op == "transfer":
            amt_val = self._validate_number_field(amt_raw, "amt")
            result["amt"] = amt_val
            result["to"] = to_str or "Odbiorca"
        elif op == "link":
            result["addr"] = addr_str or "AdresPortfela"

        return result

    def build_json_from_form(self):
        try:
            j = self._build_json_from_form_internal()
            self.json_text.delete("1.0", "end")
            self.json_text.insert(
                "1.0",
                json.dumps(j, ensure_ascii=False, separators=(",", ":")),
            )
        except Exception as e:
            messagebox.showerror("Builder error", str(e))

    # ----- encode / decode CBOR -----

    def encode_cbor(self):
        if cbor2 is None:
            messagebox.showerror(
                "CBOR error",
                "Biblioteka cbor2 nie jest zainstalowana.\n"
                "Uruchom: pip install cbor2",
            )
            return
        try:
            raw = self.json_text.get("1.0", "end").strip()
            obj = json.loads(raw)
            if "p" not in obj:
                obj["p"] = "lora20"
            cbor_bytes = cbor2.dumps(obj)
            length = len(cbor_bytes)
            dc = calc_dc_cost(length)
            hex_str = cbor_bytes.hex().upper()

            if length > MAX_PAYLOAD:
                message = (
                    f"CBOR ma {length} bajtów, > {MAX_PAYLOAD}. "
                    "Możesz użyć sekcji fragmentacji poniżej."
                )
                messagebox.showwarning("CBOR payload too long", message)

            self.cbor_bytes_label.config(text=f"📦 CBOR bytes: {length}")
            self.cbor_dc_label.config(text=f"💸 DC cost: {dc}")
            self.cbor_hex_entry.delete(0, "end")
            self.cbor_hex_entry.insert(0, hex_str)

            self._last_cbor_bytes = cbor_bytes
        except Exception as e:
            messagebox.showerror("CBOR encode error", str(e))

    def decode_cbor(self):
        if cbor2 is None:
            messagebox.showerror(
                "CBOR error",
                "Biblioteka cbor2 nie jest zainstalowana.\n"
                "Uruchom: pip install cbor2",
            )
            return
        try:
            raw_hex = self.cbor_hex_entry.get().strip().replace(" ", "")
            if raw_hex == "":
                raise ValueError("CBOR hex is empty")
            if len(raw_hex) % 2 != 0:
                raise ValueError("CBOR hex length must be even")

            data = bytes.fromhex(raw_hex)
            length = len(data)
            dc = calc_dc_cost(length)

            obj = cbor2.loads(data)
            text = json.dumps(obj, ensure_ascii=False, separators=(",", ":"))

            self.cbor_decoded_text.delete("1.0", "end")
            self.cbor_decoded_text.insert("1.0", text)
            self.cbor_bytes_label.config(text=f"📦 CBOR bytes: {length}")
            self.cbor_dc_label.config(text=f"💸 DC cost: {dc}")
            self._last_cbor_bytes = data
        except Exception as e:
            messagebox.showerror("CBOR decode error", str(e))

    # ----- fragmentacja -----

    def build_fragments(self):
        if cbor2 is None:
            messagebox.showerror(
                "CBOR error",
                "Biblioteka cbor2 nie jest zainstalowana.\n"
                "Uruchom: pip install cbor2",
            )
            return

        try:
            cbor_bytes = getattr(self, "_last_cbor_bytes", None)
            if cbor_bytes is None:
                raw_hex = self.cbor_hex_entry.get().strip().replace(" ", "")
                if raw_hex:
                    cbor_bytes = bytes.fromhex(raw_hex)
                else:
                    raw = self.json_text.get("1.0", "end").strip()
                    obj = json.loads(raw)
                    if "p" not in obj:
                        obj["p"] = "lora20"
                    cbor_bytes = cbor2.dumps(obj)

            total_len = len(cbor_bytes)
            frags = fragment_cbor(cbor_bytes, MAX_PAYLOAD, msg_id=1)

            self.frag_text.delete("1.0", "end")
            for i, frag in enumerate(frags):
                hex_str = frag.hex().upper()
                self.frag_text.insert(
                    "end",
                    f"Fragment {i}/{len(frags)-1} (len={len(frag)}B): {hex_str}\n",
                )

            self.frag_info_label.config(
                text=f"Utworzono {len(frags)} fragmentów z {total_len} bajtów CBOR."
            )

            reassembled = reassemble_fragments(frags)
            if reassembled != cbor_bytes:
                self.frag_text.insert(
                    "end", "\n[WARN] Reassembled bytes różnią się od oryginału!\n"
                )
        except Exception as e:
            messagebox.showerror("Fragmentation error", str(e))


if __name__ == "__main__":
    app = Lora20GUI()
    app.mainloop()
