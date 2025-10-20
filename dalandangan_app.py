import tkinter as tk
from tkinter import ttk, messagebox, simpledialog
import mysql.connector
import hashlib
from datetime import date
from reportlab.lib.pagesizes import A4
from reportlab.pdfgen import canvas
import ttkbootstrap as tb
from PIL import Image, ImageTk
import os
import re

# --------- DB CONFIG ----------
DB_CONFIG = {
    'host': '127.0.0.1',
    'user': 'root',
    'password': '',
    'database': 'dalandangan_db'
}

def db_connect():
    return mysql.connector.connect(**DB_CONFIG)

def hash_password(pw: str):
    return hashlib.sha256(pw.encode()).hexdigest()

# --------- DB Helpers ----------
def fetch_one(query, params=()):
    conn = db_connect(); cur = conn.cursor(dictionary=True)
    cur.execute(query, params)
    res = cur.fetchone()
    cur.close(); conn.close()
    return res

def fetch_all(query, params=()):
    conn = db_connect(); cur = conn.cursor(dictionary=True)
    cur.execute(query, params)
    res = cur.fetchall()
    cur.close(); conn.close()
    return res

def execute(query, params=()):
    conn = db_connect(); cur = conn.cursor()
    cur.execute(query, params)
    conn.commit()
    lastid = cur.lastrowid
    cur.close(); conn.close()
    return lastid

# --------- Main Application ----------
class DalandanganApp(tb.Window):
    def __init__(self):
        super().__init__(themename="flatly")
        self.title("🍕 Dalandangan Pizza Restaurant")
        self.state('zoomed')
        self.current_user = None
        # cart mapping product_id -> {'product': dict, 'qty': int}
        self.cart = {}

        style = ttk.Style()
        style.configure("card.TFrame", background="#f15d22", relief="solid", borderwidth=2)
        style.configure("TButton", font=("Helvetica", 14, "bold"), padding=10)
        style.configure("TLabel", font=("Helvetica", 14))
        style.configure("TNotebook.Tab", font=("Helvetica", 16, "bold"), padding=[20, 10])

        # folder where your pizza images live
        self.images_dir = os.path.join("images", "pizzas")
        # optional default image path (if you add default_pizza.jpg)
        self.default_image = os.path.join(self.images_dir, "default_pizza.jpg") if os.path.exists(os.path.join(self.images_dir, "default_pizza.jpg")) else None

        self._product_photos = {}  # cache images to avoid GC

        self._show_login_screen()

    def _clear(self):
        for w in self.winfo_children():
            w.destroy()

    # ---------- LOGIN ----------
    def _show_login_screen(self):
        self._clear()
        container = ttk.Frame(self, padding=20)
        container.pack(fill="both", expand=True)

        logo_frame = ttk.Frame(container)
        logo_frame.pack(pady=(40, 10))

        try:
            img = Image.open("logo.png").resize((350, 300))
            logo = ImageTk.PhotoImage(img)
            lbl_logo = ttk.Label(logo_frame, image=logo, background="#ffffff")
            lbl_logo.image = logo
            lbl_logo.pack()
        except:
            ttk.Label(logo_frame, text="🍕 Pizzara Dalandangan", font=("Helvetica", 36, "bold"), foreground="darkred").pack()

        form_frame = ttk.Frame(container, padding=10)
        form_frame.pack(pady=10)

        ttk.Label(form_frame, text="Username:", font=("Helvetica", 18, "bold")).grid(row=0, column=0, padx=10, pady=10, sticky="e")
        user_entry = ttk.Entry(form_frame, width=25, bootstyle="info", font=("Helvetica", 16))
        user_entry.grid(row=0, column=1, padx=10, pady=10)

        ttk.Label(form_frame, text="Password:", font=("Helvetica", 18, "bold")).grid(row=1, column=0, padx=10, pady=10, sticky="e")
        pw_entry = ttk.Entry(form_frame, width=25, show="*", bootstyle="info", font=("Helvetica", 16))
        pw_entry.grid(row=1, column=1, padx=10, pady=10)

        def do_login():
            uname, pw = user_entry.get().strip(), pw_entry.get().strip()
            user = fetch_one("SELECT * FROM users WHERE username=%s", (uname,))
            if user and user['password_hash'] == hash_password(pw):
                self.current_user = user
                role = user.get('role', 'customer')
                self.cart = {}  # reset cart on login
                if role == 'customer':
                    self._show_customer_dashboard()
                elif role == 'cashier':
                    self._show_cashier_dashboard()
                elif role == 'staff':
                    self._show_staff_dashboard()
                else:
                    messagebox.showerror("Role Error", "Unknown user role.")
            else:
                messagebox.showerror("Login Failed", "Invalid credentials")

        btn_frame = ttk.Frame(container)
        btn_frame.pack(pady=20)
        ttk.Button(btn_frame, text="Login", bootstyle="danger", width=22, command=do_login).pack(pady=8)
        ttk.Button(btn_frame, text="Register", bootstyle="warning", width=22, command=self._show_register_screen).pack(pady=5)

    # ---------- REGISTER ----------
    def _show_register_screen(self):
        self._clear()
        frame = ttk.Frame(self, padding=30, style="card.TFrame")
        frame.place(relx=0.5, rely=0.5, anchor="center")
        ttk.Label(frame, text="📝 Customer Registration", font=("Helvetica", 26, "bold"), foreground="darkorange").pack(pady=15)
        fields = ["Username", "Password", "Full Name", "Email"]
        entries = {}
        for f in fields:
            ttk.Label(frame, text=f).pack(pady=4)
            e = ttk.Entry(frame, width=40, show="*" if f == "Password" else None, bootstyle="info")
            e.pack(pady=4)
            entries[f.lower().replace(" ", "_")] = e

        def register():
            username, pw = entries['username'].get(), entries['password'].get()
            if not username or not pw:
                return messagebox.showerror("Error", "Fill required fields")
            try:
                execute(
                    "INSERT INTO users (username,password_hash,full_name,email,role) VALUES (%s,%s,%s,%s,'customer')",
                    (username, hash_password(pw), entries['full_name'].get(), entries['email'].get())
                )
                messagebox.showinfo("OK", "Registered! Please login.")
                self._show_login_screen()
            except mysql.connector.IntegrityError:
                messagebox.showerror("Error", "Username already exists.")

        ttk.Button(frame, text="Create Account", bootstyle="success", width=25, command=register).pack(pady=12)
        ttk.Button(frame, text="Back", bootstyle="secondary", width=25, command=self._show_login_screen).pack(pady=6)

    # ---------- CUSTOMER DASHBOARD ----------
    def _show_customer_dashboard(self):
        self._clear()
        self.cart = {}  # reset cart
        nb = ttk.Notebook(self)
        nb.pack(fill="both", expand=True, padx=20, pady=20)

        # --- Browse Menu ---
        browse_frame = ttk.Frame(nb, padding=10, style="card.TFrame")
        nb.add(browse_frame, text="Browse Menu")
        ttk.Label(browse_frame, text=f"🍴 Welcome {self.current_user['username']}", font=("Helvetica", 22, "bold"), foreground="darkred").pack(pady=15)

        canvas = tk.Canvas(browse_frame)
        scroll_y = ttk.Scrollbar(browse_frame, orient="vertical", command=canvas.yview)
        scroll_frame = ttk.Frame(canvas)
        canvas.create_window((0, 0), window=scroll_frame, anchor="nw")
        canvas.configure(yscrollcommand=scroll_y.set)
        canvas.pack(side="left", fill="both", expand=True)
        scroll_y.pack(side="right", fill="y")

        # cache product photos so garbage collector doesn't remove them
        self._product_photos = {}

        # ---------- IMAGE RESOLUTION FIX ----------
        def find_image_for_product(p):
            """
            Priority:
             1) product['image_path'] (if not NULL and file exists)
             2) images/pizzas/<product_name_clean>.(jpg|jpeg|png)
             3) default image (if present)
             4) None (caller will show fallback emoji)
            """
            # 1) database-provided path
            try:
                db_path = p.get('image_path')
                if db_path and isinstance(db_path, str) and db_path.strip() and os.path.exists(db_path):
                    return db_path
            except Exception:
                pass

            # 2) guess by product name
            name = (p.get('name') or "").strip()
            if name:
                # create safe filename: pepperoni classic -> pepperoni_classic
                safe = re.sub(r'[^a-z0-9]+', '_', name.strip().lower()).strip('_')
                for ext in (".jpg", ".jpeg", ".png"):
                    candidate = os.path.join(self.images_dir, safe + ext)
                    if os.path.exists(candidate):
                        return candidate

            # 3) default image if available
            if self.default_image and os.path.exists(self.default_image):
                return self.default_image

            return None
        # ---------- END IMAGE RESOLUTION FIX ----------

        def add_to_cart(product, qty):
            pid = product['id']
            if pid in self.cart:
                self.cart[pid]['qty'] += qty
            else:
                self.cart[pid] = {'product': product, 'qty': qty}
            messagebox.showinfo("Cart", f"Added {qty} x {product['name']} to cart.")
            refresh_cart_tree()

        def open_qty_modal(product):
            win = tb.Toplevel(self); win.title("Add to Cart")
            ttk.Label(win, text=f"{product['name']} (₱{product['price']})", font=("Helvetica", 14, "bold")).pack(pady=8)
            qty_var = tk.IntVar(value=1)
            ttk.Label(win, text="Quantity").pack()
            ttk.Entry(win, textvariable=qty_var, width=10).pack(pady=5)
            def on_add():
                try:
                    q = int(qty_var.get()); 
                    if q <= 0: raise ValueError
                except:
                    messagebox.showerror("Invalid", "Quantity must be a positive integer."); return
                add_to_cart(product, q); win.destroy()
            ttk.Button(win, text="Add to Cart", bootstyle="success", command=on_add).pack(pady=10)

        def populate_menu():
            products = fetch_all("SELECT * FROM products WHERE available=1")
            # dedupe by name to avoid duplicate product entries in UI
            seen_names = set()
            col = 0; row = 0
            for p in products:
                name = (p.get('name') or "").strip()
                if not name:
                    continue
                if name in seen_names:
                    continue
                seen_names.add(name)

                card = ttk.Frame(scroll_frame, padding=12, style="card.TFrame")
                card.grid(row=row, column=col, padx=14, pady=14)

                # Use find_image_for_product to decide which image to show
                img_shown = False
                img_path = find_image_for_product(p)
                if img_path:
                    try:
                        img = Image.open(img_path).resize((160,160))
                        photo = ImageTk.PhotoImage(img)
                        self._product_photos[p['id']] = photo
                        lbl = ttk.Label(card, image=photo)
                        lbl.image = photo
                        lbl.pack()
                        img_shown = True
                    except Exception:
                        img_shown = False

                if not img_shown:
                    # fallback large emoji if no image
                    ttk.Label(card, text="🍕", font=("Helvetica", 48)).pack(pady=6)

                ttk.Label(card, text=p['name'], font=("Helvetica", 16, "bold"), foreground="darkorange").pack(pady=6)
                ttk.Label(card, text=f"₱{p['price']:.2f}", font=("Helvetica", 14), foreground="red").pack()
                ttk.Button(card, text="➕ Add to Cart", bootstyle="success", width=20,
                           command=lambda prod=p: open_qty_modal(prod)).pack(pady=8)
                col += 1
                if col >= 3:
                    col = 0; row += 1

        scroll_frame.bind("<Configure>", lambda e: canvas.configure(scrollregion=canvas.bbox("all")))
        populate_menu()

        # --- My Cart Tab ---
        cart_frame = ttk.Frame(nb, padding=10)
        nb.add(cart_frame, text="🛒 My Cart")

        cart_tree = ttk.Treeview(cart_frame, columns=("product", "qty", "unit_price", "subtotal"), show="headings", height=10)
        for col, w in [("product", 300), ("qty", 80), ("unit_price", 120), ("subtotal", 120)]:
            cart_tree.heading(col, text=col.title())
            cart_tree.column(col, anchor="center", width=w)
        cart_tree.pack(fill="x", padx=20, pady=10)

        def refresh_cart_tree():
            cart_tree.delete(*cart_tree.get_children())
            for pid, data in self.cart.items():
                prod = data['product']; qty = data['qty']; subtotal = prod['price'] * qty
                cart_tree.insert("", "end", iid=str(pid), values=(prod['name'], qty, f"₱{prod['price']:.2f}", f"₱{subtotal:.2f}"))
            update_cart_totals()

        def update_cart_totals():
            total = sum(d['product']['price'] * d['qty'] for d in self.cart.values())
            lbl_total.config(text=f"Total: ₱{total:.2f}")

        def remove_selected():
            sel = cart_tree.focus()
            if not sel: return
            pid = int(sel)
            if pid in self.cart: del self.cart[pid]
            refresh_cart_tree()

        def change_qty():
            sel = cart_tree.focus()
            if not sel: return
            pid = int(sel)
            if pid not in self.cart: return
            win = tb.Toplevel(self); win.title("Change Quantity")
            qty_var = tk.IntVar(value=self.cart[pid]['qty'])
            ttk.Label(win, text="Quantity").pack(pady=6)
            ttk.Entry(win, textvariable=qty_var, width=12).pack(pady=6)
            def apply_qty():
                try:
                    q = int(qty_var.get()); 
                    if q <= 0: raise ValueError
                except:
                    messagebox.showerror("Invalid", "Quantity must be a positive integer."); return
                self.cart[pid]['qty'] = q; refresh_cart_tree(); win.destroy()
            ttk.Button(win, text="Apply", bootstyle="success", command=apply_qty).pack(pady=8)

        def checkout():
            if not self.cart:
                messagebox.showwarning("Empty Cart", "Your cart is empty."); return
            win = tb.Toplevel(self); win.title("Checkout")
            ttk.Label(win, text="Checkout", font=("Helvetica", 16, "bold")).pack(pady=8)
            addr = tk.StringVar(); phone = tk.StringVar(); method = tk.StringVar(value="Cash")
            ttk.Label(win, text="Delivery Address").pack(); ttk.Entry(win, textvariable=addr, width=50).pack(pady=4)
            ttk.Label(win, text="Contact Number").pack(); ttk.Entry(win, textvariable=phone, width=30).pack(pady=4)
            ttk.Label(win, text="Payment Method").pack(); ttk.Combobox(win, values=["Cash", "Online"], textvariable=method, width=20).pack(pady=6)

            summary = tk.Text(win, height=8, width=60, state="normal")
            summary.insert("end", "Items:\n")
            total_amt = 0
            for d in self.cart.values():
                name = d['product']['name']; q = d['qty']; sub = d['product']['price']*q
                summary.insert("end", f"{name} x{q} — ₱{sub:.2f}\n"); total_amt += sub
            summary.insert("end", f"\nTotal: ₱{total_amt:.2f}")
            summary.config(state="disabled"); summary.pack(pady=8)

            def do_confirm():
                if not addr.get().strip() or not phone.get().strip():
                    messagebox.showerror("Missing", "Please fill address and contact number."); return
                oid = execute("INSERT INTO orders (user_id,total,delivery_address,contact_number,payment_method,status) VALUES (%s,%s,%s,%s,%s,'Pending')",
                              (self.current_user['id'], total_amt, addr.get(), phone.get(), method.get()))
                for d in self.cart.values():
                    execute("INSERT INTO order_items (order_id,product_id,qty,unit_price) VALUES (%s,%s,%s,%s)",
                            (oid, d['product']['id'], d['qty'], d['product']['price']))
                payment_status = "Paid" if method.get() == "Cash" else "Pending"
                execute("INSERT INTO payments (order_id,amount,method,status,paid_at) VALUES (%s,%s,%s,%s,NOW())",
                        (oid, total_amt, method.get(), payment_status))
                messagebox.showinfo("Order Placed", f"Order #{oid} placed successfully.\nTotal: ₱{total_amt:.2f}")
                self.cart = {}; refresh_cart_tree(); win.destroy()

            ttk.Button(win, text="Confirm Order", bootstyle="success", command=do_confirm).pack(pady=6)

        controls = ttk.Frame(cart_frame); controls.pack(pady=6)
        ttk.Button(controls, text="Change Qty", bootstyle="warning", command=change_qty).pack(side="left", padx=6)
        ttk.Button(controls, text="Remove Item", bootstyle="danger", command=remove_selected).pack(side="left", padx=6)
        ttk.Button(controls, text="Checkout", bootstyle="success", command=checkout).pack(side="left", padx=6)
        lbl_total = ttk.Label(cart_frame, text="Total: ₱0.00", font=("Helvetica", 14, "bold")); lbl_total.pack(pady=8)

        # --- Track Orders Tab ---
        track_frame = ttk.Frame(nb, padding=10, style="card.TFrame")
        nb.add(track_frame, text="Track Orders")
        ttk.Label(track_frame, text="📦 Your Orders", font=("Helvetica", 18, "bold"), foreground="darkorange").pack(pady=10)

        tree2 = ttk.Treeview(track_frame, columns=("status","delivery_status","delivery_person","total","date"),
                             show="headings", height=10)
        for col in ("status","delivery_status","delivery_person","total","date"):
            tree2.heading(col, text=col.replace("_", " ").title()); tree2.column(col, anchor="center", width=180)
        tree2.pack(fill="x", expand=False, padx=40, pady=20)

        def load_orders_customer():
            tree2.delete(*tree2.get_children())
            rows = fetch_all("""
                SELECT o.*,
                       (SELECT d.status FROM deliveries d WHERE d.order_id=o.id LIMIT 1) AS delivery_status,
                       (SELECT d.delivery_person FROM deliveries d WHERE d.order_id=o.id LIMIT 1) AS delivery_person
                FROM orders o WHERE o.user_id=%s ORDER BY o.created_at DESC
            """, (self.current_user['id'],))
            for r in rows:
                delivery = r['delivery_status'] or "Not yet dispatched"
                person = r['delivery_person'] or "N/A"
                tree2.insert("", "end", iid=r['id'], values=(r['status'], delivery, person, f"₱{r['total']}", r['created_at']))
        load_orders_customer()

        ttk.Button(self, text="Logout", bootstyle="danger", width=20, command=self._logout).pack(side="right", padx=20, pady=20, anchor="se")

    # ---------- STAFF DASHBOARD ----------
    def _show_staff_dashboard(self):
        self._clear()
        ttk.Label(self, text="👨‍🍳 Staff Panel", font=("Helvetica", 22, "bold"), foreground="darkorange").pack(pady=15)

        # ----- Unique Table Styling for Staff -----
        style = ttk.Style()
        style.configure("Staff.Treeview",
                        rowheight=35,
                        font=("Helvetica", 13, "bold"),
                        padding=6)
        style.configure("Staff.Treeview.Heading",
                        font=("Helvetica", 14, "bold"),
                        anchor="center")

        # ----- Table Frame -----
        frame = ttk.Frame(self, padding=20, style="card.TFrame")
        frame.pack(pady=10)

        # ----- Treeview -----
        tree = ttk.Treeview(
            frame,
            style="Staff.Treeview",
            columns=("customer", "status", "total"),
            show="headings",
            height=15
        )

        # Headings
        tree.heading("customer", text="Customer")
        tree.heading("status", text="Status")
        tree.heading("total", text="Total")

        # Center text and set widths
        tree.column("customer", anchor="center", width=250)
        tree.column("status", anchor="center", width=250)
        tree.column("total", anchor="center", width=250)

        tree.pack(fill="x", expand=False, padx=40, pady=20)

        def load_orders():
            tree.delete(*tree.get_children())
            rows = fetch_all("""
                SELECT o.*, u.full_name 
                FROM orders o 
                JOIN users u ON o.user_id=u.id 
                WHERE status IN ('Pending','Preparing')
            """)
            for r in rows:
                cname = r['full_name'] or "Unknown"
                tree.insert("", "end", iid=r['id'],
                            values=(cname, r['status'], f"₱{r['total']}"))

        def mark_preparing():
            oid = tree.focus()
            if not oid:
                return
            execute("UPDATE orders SET status='Preparing' WHERE id=%s", (oid,))
            load_orders()

        def mark_ready():
            oid = tree.focus()
            if not oid:
                return
            execute("UPDATE orders SET status='Ready for Delivery' WHERE id=%s", (oid,))
            load_orders()

        btn_frame = ttk.Frame(self)
        btn_frame.pack(pady=20)

        ttk.Button(btn_frame, text="➡ Preparing", bootstyle="warning", width=20,
                   command=mark_preparing).pack(side="left", padx=10)
        ttk.Button(btn_frame, text="✅ Ready", bootstyle="success", width=20,
                   command=mark_ready).pack(side="left", padx=10)
        ttk.Button(btn_frame, text="🔄 Refresh", bootstyle="secondary", width=20,
                   command=load_orders).pack(side="left", padx=10)

        ttk.Button(self, text="Logout", bootstyle="danger", width=20,
                   command=self._logout).pack(side="right", padx=20, pady=20, anchor="se")

        load_orders()

    # ---------- CASHIER DASHBOARD ----------
    def _show_cashier_dashboard(self):
        self._clear()
        ttk.Label(
            self,
            text="💰 Cashier/Admin Panel",
            font=("Helvetica", 22, "bold"),
            foreground="red"
        ).pack(pady=15)

        frame = ttk.Frame(self, padding=20)
        frame.pack(fill="both", expand=True)

        center_frame = ttk.Frame(frame)
        center_frame.pack(expand=True)

        table_frame = ttk.Frame(center_frame)
        table_frame.pack()

        scrollbar = ttk.Scrollbar(table_frame)
        scrollbar.pack(side="right", fill="y")

        tree = ttk.Treeview(
            table_frame,
            columns=("status", "delivery_person", "total", "payment_method", "payment_status"),
            show="headings",
            height=20,
            yscrollcommand=scrollbar.set
        )
        scrollbar.config(command=tree.yview)

        tree.heading("status", text="Status")
        tree.heading("delivery_person", text="Delivery Person")
        tree.heading("total", text="Total")
        tree.heading("payment_method", text="Payment Method")
        tree.heading("payment_status", text="Payment Status")

        tree.column("status", anchor="center", width=250)
        tree.column("delivery_person", anchor="center", width=150)
        tree.column("total", anchor="center", width=120)
        tree.column("payment_method", anchor="center", width=150)
        tree.column("payment_status", anchor="center", width=150)

        style = ttk.Style()
        style.configure("Treeview.Heading", font=("Helvetica", 10, "bold"), anchor="center")
        style.configure("Treeview", font=("Helvetica", 10), anchor="center")

        tree.pack()

        def load_orders():
            tree.delete(*tree.get_children())
            rows = fetch_all("""
                SELECT o.*, 
                       (SELECT d.status FROM deliveries d WHERE d.order_id=o.id LIMIT 1) AS delivery_status,
                       (SELECT d.delivery_person FROM deliveries d WHERE d.order_id=o.id LIMIT 1) AS delivery_person,
                       (SELECT p.method FROM payments p WHERE p.order_id=o.id LIMIT 1) AS payment_method,
                       (SELECT p.status FROM payments p WHERE p.order_id=o.id LIMIT 1) AS payment_status
                FROM orders o ORDER BY o.created_at DESC
            """)
            for r in rows:
                status = f"{r['status']} ({r['delivery_status']})" if r['delivery_status'] else r['status']
                person = r['delivery_person'] or "N/A"
                method = r['payment_method'] or "N/A"
                pay_status = r['payment_status'] or "Pending"
                iid = r['id']
                tree.insert("", "end", iid=iid, values=(status, person, f"₱{r['total']}", method, pay_status))

        load_orders()

        def dispatch_order():
            oid = tree.focus()
            if not oid: return
            delivery_person = simpledialog.askstring("Delivery Person", "Enter delivery person name:")
            if not delivery_person: return
            execute("""INSERT INTO deliveries (order_id, delivery_person, pickup_time, status) 
                       VALUES (%s,%s,NOW(),'Picked Up')""", (oid, delivery_person))
            execute("UPDATE orders SET status='Out for Delivery' WHERE id=%s", (oid,))
            messagebox.showinfo("Dispatched", f"Order #{oid} assigned to {delivery_person}")
            load_orders()

        def mark_delivered():
            oid = tree.focus()
            if not oid: return
            execute("UPDATE deliveries SET delivered_at=NOW(), status='Delivered' WHERE order_id=%s", (oid,))
            execute("UPDATE orders SET status='Completed' WHERE id=%s", (oid,))
            messagebox.showinfo("Delivered", f"Order #{oid} marked as Delivered")
            load_orders()

        def mark_as_paid():
            oid = tree.focus()
            if not oid:
                messagebox.showwarning("Select Order", "Please select an order first."); return
            payment = fetch_one("SELECT * FROM payments WHERE order_id=%s", (oid,))
            if not payment:
                messagebox.showerror("Error", "No payment record found for this order."); return
            if payment['status'] == "Paid":
                messagebox.showinfo("Info", "Already marked as Paid."); return
            execute("UPDATE payments SET status='Paid', paid_at=NOW() WHERE order_id=%s", (oid,))
            messagebox.showinfo("Success", f"Order #{oid} marked as Paid."); load_orders()

        def generate_receipt():
            oid = tree.focus()
            if not oid: return
            o = fetch_one("""SELECT o.*, u.full_name,
                                    (SELECT d.delivery_person FROM deliveries d WHERE d.order_id=o.id LIMIT 1) AS delivery_person
                             FROM orders o JOIN users u ON o.user_id=u.id 
                             WHERE o.id=%s""", (oid,))
            items = fetch_all("""SELECT oi.*, p.name 
                                 FROM order_items oi 
                                 JOIN products p ON oi.product_id=p.id 
                                 WHERE oi.order_id=%s""", (oid,))
            fname = f"receipt_order_{oid}.pdf"
            c = canvas.Canvas(fname, pagesize=A4)
            width, height = A4
            y = height - 50
            c.setFont("Helvetica-Bold", 16)
            c.drawString(180, y, "🍕 Dalandangan Pizza Receipt")
            y -= 40
            c.setFont("Helvetica", 12)
            c.drawString(50, y, f"Order ID: {o['id']}")
            y -= 20
            c.drawString(50, y, f"Customer: {o['full_name']}")
            y -= 20
            c.drawString(50, y, f"Address: {o['delivery_address']}")
            y -= 20
            c.drawString(50, y, f"Payment: {o['payment_method']}")
            y -= 20
            c.drawString(50, y, f"Delivery Person: {o['delivery_person'] or 'N/A'}")
            y -= 30
            c.drawString(50, y, "Items:")
            y -= 20
            for it in items:
                c.drawString(60, y, f"{it['name']} x{it['qty']} - ₱{it['unit_price']*it['qty']}")
                y -= 20
            y -= 10
            c.drawString(50, y, f"Total: ₱{o['total']:.2f}")
            y -= 40
            c.drawString(200, y, "Thank you for your order!")
            c.showPage()
            c.save()
            messagebox.showinfo("Receipt", f"Saved receipt as {fname}")

        btn_frame = ttk.Frame(self)
        btn_frame.pack(pady=12)
        ttk.Button(btn_frame, text="🚚 Dispatch", bootstyle="warning", width=18, command=dispatch_order).pack(side="left", padx=8)
        ttk.Button(btn_frame, text="✅ Delivered", bootstyle="success", width=18, command=mark_delivered).pack(side="left", padx=8)
        ttk.Button(btn_frame, text="💵 Mark as Paid", bootstyle="success", width=18, command=mark_as_paid).pack(side="left", padx=8)
        ttk.Button(btn_frame, text="🧾 Receipt", bootstyle="info", width=18, command=generate_receipt).pack(side="left", padx=8)
        ttk.Button(btn_frame, text="🔄 Refresh", bootstyle="secondary", width=18, command=load_orders).pack(side="left", padx=8)

        ttk.Button(self, text="Logout", bootstyle="danger", width=20, command=self._logout).pack(side="right", padx=20, pady=20, anchor="se")

    # ---------- LOGOUT ----------
    def _logout(self):
        self.current_user = None
        self.cart = {}
        self._show_login_screen()

# --------- Run ----------
if __name__ == "__main__":
    app = DalandanganApp()
    app.mainloop()
