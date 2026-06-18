import customtkinter as ctk
from tkinter import ttk, messagebox
from datetime import datetime
import threading
import os
from PIL import Image

from database import (
    init_db, agregar_transaccion, listar_transacciones,
    eliminar_transaccion, obtener_portfolio,
)
from fondos import (
    obtener_info_fondo, obtener_precio_actual, obtener_precio_historico_en_fecha,
    obtener_datos_historicos,
    generar_grafico_pnl_linea,
    obtener_tipo_cambio, convertir_a_eur
)
from concurrent.futures import ThreadPoolExecutor, as_completed
from database import obtener_resumen_isin

ctk.set_appearance_mode("dark")
ctk.set_default_color_theme("green")


def formatear(valor):
    if valor is None:
        return "---"
    return f"€{valor:,.2f}"



class App(ctk.CTk):
    def __init__(self):
        super().__init__()
        init_db()
        self.title("Silvestor - Control de Fondos de Inversión")
        self.geometry("1100x700")
        self._info_fondo_cache = {}

        self.grid_rowconfigure(0, weight=0)
        self.grid_rowconfigure(1, weight=1)
        self.grid_columnconfigure(0, weight=1)

        self._build_header()
        self._build_tabs()
        self._build_statusbar()

    def _obtener_tc(self):
        if not hasattr(self, "_tc") or self._tc is None:
            self._tc = obtener_tipo_cambio()
        return self._tc

    def _build_header(self):
        header = ctk.CTkFrame(self, corner_radius=0, height=50)
        header.grid(row=0, column=0, sticky="ew", padx=0, pady=0)
        header.grid_columnconfigure(0, weight=1)
        ctk.CTkLabel(header, text="Silvestor", font=("Segoe UI", 22, "bold")).pack(side="left", padx=20, pady=8)
        ctk.CTkLabel(header, text="Seguimiento de fondos de inversión", font=("Segoe UI", 13)).pack(side="left", padx=5)

    def _build_tabs(self):
        self.tabview = ctk.CTkTabview(self, command=self._on_tab_change)
        self.tabview.grid(row=1, column=0, sticky="nsew", padx=10, pady=(5, 0))

        self.tab_agregar = self.tabview.add("Agregar")
        self.tab_inversiones = self.tabview.add("Inversiones")
        self.tab_rendimiento = self.tabview.add("Rendimiento")

        self._build_tab_agregar()
        self._build_tab_inversiones()
        self._build_tab_rendimiento()

    def _on_tab_change(self, tab_name):
        if tab_name == "Rendimiento":
            self._cargar_lista_rendimientos()

    def _build_statusbar(self):
        self.statusbar = ctk.CTkLabel(self, text="Listo", anchor="w", font=("Segoe UI", 11))
        self.statusbar.grid(row=2, column=0, sticky="ew", padx=10, pady=(2, 5))

    def set_status(self, msg):
        if hasattr(self, "statusbar"):
            self.statusbar.configure(text=msg)

    def _build_tab_agregar(self):
        self.tab_agregar.grid_columnconfigure(0, weight=2)
        self.tab_agregar.grid_columnconfigure(1, weight=3)

        entrada = ctk.CTkFrame(self.tab_agregar, fg_color="transparent")
        entrada.grid(row=0, column=0, columnspan=2, sticky="nsew", padx=15, pady=10)

        entrada.grid_columnconfigure(0, weight=1)
        entrada.grid_columnconfigure(1, weight=2)

        row = 0
        ctk.CTkLabel(entrada, text="ISIN", font=("Segoe UI", 13, "bold")).grid(row=row, column=0, sticky="w", pady=(10, 2))
        self.entry_isin = ctk.CTkEntry(entrada, placeholder_text="Ej: LU0635178014")
        self.entry_isin.grid(row=row, column=1, sticky="ew", pady=(10, 2))

        row += 1
        ctk.CTkLabel(entrada, text="Participaciones", font=("Segoe UI", 13, "bold")).grid(row=row, column=0, sticky="w", pady=2)
        self.entry_participaciones = ctk.CTkEntry(entrada, placeholder_text="Número de participaciones")
        self.entry_participaciones.grid(row=row, column=1, sticky="ew", pady=2)

        row += 1
        ctk.CTkLabel(entrada, text="Fecha", font=("Segoe UI", 13, "bold")).grid(row=row, column=0, sticky="w", pady=2)
        self.entry_fecha = ctk.CTkEntry(entrada, placeholder_text="YYYY-MM-DD (dejar vacío = hoy)")
        self.entry_fecha.grid(row=row, column=1, sticky="ew", pady=2)

        row += 1
        ctk.CTkLabel(entrada, text="Tipo", font=("Segoe UI", 13, "bold")).grid(row=row, column=0, sticky="w", pady=2)
        self.combo_tipo = ctk.CTkComboBox(entrada, values=["compra", "venta"], state="readonly")
        self.combo_tipo.set("compra")
        self.combo_tipo.grid(row=row, column=1, sticky="ew", pady=2)

        row += 1
        f_btn = ctk.CTkFrame(entrada, fg_color="transparent")
        f_btn.grid(row=row, column=0, columnspan=2, pady=(15, 5))
        self.btn_preview = ctk.CTkButton(f_btn, text="Previsualizar", command=self._previsualizar)
        self.btn_preview.pack(side="left", padx=5)
        self.btn_agregar = ctk.CTkButton(f_btn, text="Agregar Transacción", state="disabled", command=self._agregar_transaccion)
        self.btn_agregar.pack(side="left", padx=5)

        self.preview_frame = ctk.CTkFrame(self.tab_agregar, fg_color="#1a1a1a", corner_radius=8)
        self.preview_frame.grid(row=1, column=0, columnspan=2, sticky="ew", padx=15, pady=5)
        self.preview_frame.grid_columnconfigure(0, weight=1)
        self.preview_frame.grid_columnconfigure(1, weight=1)
        for i in range(5):
            self.preview_frame.grid_rowconfigure(i, weight=0)
        self._ocultar_preview()

        self._info_preview = {}

    def _ocultar_preview(self):
        for w in self.preview_frame.winfo_children():
            w.destroy()
        self.preview_frame.grid_remove()

    def _mostrar_preview(self, info):
        for w in self.preview_frame.winfo_children():
            w.destroy()
        self._info_preview = info

        sep = ctk.CTkFrame(self.preview_frame, height=2, fg_color="#2e7d32")
        sep.grid(row=0, column=0, columnspan=2, sticky="ew", pady=(0, 8))

        ctk.CTkLabel(self.preview_frame, text="DATOS AUTOMÁTICOS DEL FONDO",
                      font=("Segoe UI", 12, "bold"), text_color="#2e7d32").grid(row=1, column=0, columnspan=2, sticky="w", padx=10)

        def fila(fila, label, valor, monospace=False):
            ctk.CTkLabel(self.preview_frame, text=label, font=("Segoe UI", 12)).grid(row=fila, column=0, sticky="w", padx=10, pady=1)
            fuente = ("Consolas", 12) if monospace else ("Segoe UI", 12)
            ctk.CTkLabel(self.preview_frame, text=valor, font=fuente, text_color="lightblue").grid(row=fila, column=1, sticky="w", padx=10, pady=1)

        fila(2, "Ticker FT:", info.get("ticker", "---"), monospace=True)
        fila(3, "Nombre:", info.get("nombre", "---")[:45])
        fila(4, "NAV en fecha:", info.get("nav_str", "---"))
        tc = self._obtener_tc()
        total_eur = convertir_a_eur(info.get("total", 0), tipo_cambio=tc)
        fila(5, "Total estimado:", f"€{total_eur:,.2f}" if total_eur else f"${info.get('total', 0):,.2f}")

        self.preview_frame.grid()
        self.btn_agregar.configure(state="normal")

    def _previsualizar(self):
        isin = self.entry_isin.get().strip().upper()
        fecha = self.entry_fecha.get().strip() or None
        if not isin:
            messagebox.showwarning("Aviso", "Ingresa un ISIN primero.")
            return
        try:
            participaciones = float(self.entry_participaciones.get().strip())
            if participaciones <= 0:
                raise ValueError
        except (ValueError, AttributeError):
            messagebox.showwarning("Aviso", "Ingresa un número válido de participaciones.")
            return
        if fecha:
            try:
                datetime.strptime(fecha, "%Y-%m-%d")
            except ValueError:
                messagebox.showwarning("Aviso", "Fecha inválida. Usa el formato YYYY-MM-DD.")
                return

        self.btn_preview.configure(state="disabled", text="Cargando...")
        self.set_status(f"Obteniendo datos de {isin}...")
        threading.Thread(target=self._task_preview, args=(isin, fecha, participaciones), daemon=True).start()

    def _task_preview(self, isin, fecha, participaciones):
        def fetch_info():
            if isin in self._info_fondo_cache:
                return self._info_fondo_cache[isin]
            info = obtener_info_fondo(isin)
            self._info_fondo_cache[isin] = info
            return info

        def fetch_hist():
            if not fecha:
                return None
            return obtener_precio_historico_en_fecha(isin, fecha)

        with ThreadPoolExecutor(max_workers=2) as executor:
            fut_info = executor.submit(fetch_info)
            fut_hist = executor.submit(fetch_hist)
            info = fut_info.result()
            nav_hist = fut_hist.result()

        ticker = info.get("ticker", "")
        nombre = info.get("nombre", isin)
        nav = nav_hist if nav_hist is not None else info.get("precio_actual")

        total = round(participaciones * nav, 2) if nav else 0
        tc = self._obtener_tc()
        nav_eur = convertir_a_eur(nav, tipo_cambio=tc) if nav else None
        nav_str = f"€{nav_eur:,.4f}" if nav_eur else "---"

        self.after(0, lambda: self._completar_preview(
            isin, ticker, nombre, nav, nav_str, total, fecha, participaciones
        ))

    def _completar_preview(self, isin, ticker, nombre, nav, nav_str, total, fecha, participaciones):
        self._mostrar_preview({
            "isin": isin, "ticker": ticker, "nombre": nombre,
            "nav": nav, "nav_str": nav_str, "total": total,
            "fecha": fecha, "participaciones": participaciones,
        })
        self.btn_preview.configure(state="normal", text="Previsualizar")
        self.set_status("Datos cargados. Revisa el preview y confirma.")

    def _agregar_transaccion(self):
        info = self._info_preview
        if not info:
            messagebox.showwarning("Aviso", "Haz clic en 'Previsualizar' primero.")
            return
        isin = info["isin"]
        nombre = info["nombre"]
        ticker = info.get("ticker", "")
        tipo = self.combo_tipo.get()
        fecha = info.get("fecha") or datetime.now().strftime("%Y-%m-%d")
        participaciones = info["participaciones"]
        precio = info["nav"]
        total = info["total"]

        if not nombre:
            messagebox.showwarning("Aviso", "No se pudo obtener el nombre del fondo.")
            return
        if precio is None or precio <= 0:
            messagebox.showwarning("Aviso", "No se pudo obtener el NAV en la fecha indicada.")
            return

        trans_id = agregar_transaccion(isin, nombre, tipo, participaciones, precio, total, fecha, ticker=ticker)

        tc = self._obtener_tc()
        total_eur = convertir_a_eur(total, tipo_cambio=tc)
        self.set_status(f"Transacción #{trans_id} registrada: {tipo} de {participaciones} {isin}")
        if total_eur is not None:
            messagebox.showinfo("OK", f"Transacción registrada (ID: {trans_id})\nTotal: €{total_eur:,.2f}")
        else:
            messagebox.showinfo("OK", f"Transacción registrada (ID: {trans_id})\nTotal: ${total:,.2f}")

        self.entry_isin.delete(0, "end")
        self.entry_participaciones.delete(0, "end")
        self.entry_fecha.delete(0, "end")
        self._ocultar_preview()
        self._info_preview = {}
        self.btn_agregar.configure(state="disabled")
        self.tabview.set("Inversiones")
        self._cargar_inversiones_inicial()
        self._refrescar_inversiones_background()

    def _build_tab_inversiones(self):
        self.tab_inversiones.grid_rowconfigure(0, weight=1)
        self.tab_inversiones.grid_rowconfigure(3, weight=0)
        self.tab_inversiones.grid_columnconfigure(0, weight=1)

        frame = ctk.CTkFrame(self.tab_inversiones)
        frame.grid(row=0, column=0, sticky="nsew", padx=10, pady=(10, 5))
        frame.grid_rowconfigure(0, weight=1)
        frame.grid_columnconfigure(0, weight=1)

        style = ttk.Style()
        style.theme_use("clam")
        style.configure("Treeview", rowheight=26, font=("Segoe UI", 11))
        style.configure("Treeview.Heading", font=("Segoe UI", 11, "bold"))
        style.map("Treeview", background=[("selected", "#2e7d32")])

        cols = ("id", "fecha", "isin", "nombre", "tipo", "part", "nav_compra", "nav_actual", "cambio", "total", "valor_actual")
        self.tree_inversiones = ttk.Treeview(frame, columns=cols, show="headings", height=12)
        headings = [
            ("id", "ID", 40),
            ("fecha", "Fecha", 95),
            ("isin", "ISIN", 120),
            ("nombre", "Nombre", 165),
            ("tipo", "Tipo", 65),
            ("part", "Part.", 75),
            ("nav_compra", "NAV en fecha", 100),
            ("nav_actual", "NAV actual", 90),
            ("cambio", "Cambio", 105),
            ("total", "Total", 95),
            ("valor_actual", "Valor Actual", 105),
        ]
        for col, text, width in headings:
            self.tree_inversiones.heading(col, text=text)
            self.tree_inversiones.column(col, width=width, anchor="center" if col not in ("nombre",) else "w")

        vsb = ttk.Scrollbar(frame, orient="vertical", command=self.tree_inversiones.yview)
        self.tree_inversiones.configure(yscrollcommand=vsb.set)
        self.tree_inversiones.grid(row=0, column=0, sticky="nsew")
        vsb.grid(row=0, column=1, sticky="ns")

        btn_frame = ctk.CTkFrame(self.tab_inversiones, fg_color="transparent")
        btn_frame.grid(row=1, column=0, sticky="ew", padx=10, pady=(0, 5))
        ctk.CTkButton(btn_frame, text="Actualizar NAVs", command=self._refrescar_inversiones_background).pack(side="left", padx=5)
        ctk.CTkButton(btn_frame, text="Eliminar Seleccionada", command=self._eliminar_transaccion).pack(side="right", padx=5)

        self.lbl_resumen_inv = ctk.CTkLabel(self.tab_inversiones, text="", font=("Segoe UI", 14, "bold"))
        self.lbl_resumen_inv.grid(row=2, column=0, sticky="ew", padx=15, pady=(0, 5))

        self.detalle_frame = ctk.CTkFrame(self.tab_inversiones, fg_color="#1a1a1a", corner_radius=8)
        self.detalle_frame.grid(row=3, column=0, sticky="nsew", padx=10, pady=(0, 5))
        self.detalle_frame.grid_columnconfigure(0, weight=1)
        self.detalle_frame.grid_columnconfigure(1, weight=2)
        self.detalle_frame.grid_rowconfigure(0, weight=1)
        self.detalle_frame.grid_remove()

        self.detalle_texto = ctk.CTkTextbox(self.detalle_frame, font=("Consolas", 11), width=280)
        self.detalle_texto.grid(row=0, column=0, sticky="nsew", padx=(5, 3), pady=5)

        self.detalle_img = ctk.CTkLabel(self.detalle_frame, text="Selecciona una inversión\npara ver su evolución",
                                         anchor="center", font=("Segoe UI", 12))
        self.detalle_img.grid(row=0, column=1, sticky="nsew", padx=(3, 5), pady=5)

        self.tree_inversiones.bind("<<TreeviewSelect>>", self._on_inversion_select)

        self._cargar_inversiones_inicial()
        self.after(200, self._refrescar_inversiones_background)

    def _cargar_inversiones_inicial(self):
        for row in self.tree_inversiones.get_children():
            self.tree_inversiones.delete(row)
        transacciones = listar_transacciones()
        if not transacciones:
            self.lbl_resumen_inv.configure(text="No hay transacciones. Agrega una en la pestaña 'Agregar'.")
            return
        tc = self._obtener_tc()
        total_inv_eur = 0
        for t in transacciones:
            moneda = t.get("moneda", "USD")
            part = t["participaciones"]
            precio_eur = convertir_a_eur(t["precio"], moneda, tc)
            total_eur = convertir_a_eur(t["total"], moneda, tc)
            total_inv_eur += total_eur or 0
            self.tree_inversiones.insert("", "end", values=(
                t["id"], t["fecha"], t["isin"], t["nombre"][:35], t["tipo"],
                f"{part:.4f}", formatear(precio_eur), "---", "---", formatear(total_eur), "---",
            ))
        self.lbl_resumen_inv.configure(text=f"Total invertido: {formatear(total_inv_eur)}  |  Actualizando NAVs...")
        self.set_status("Cargando datos iniciales...")

    def _refrescar_inversiones_background(self):
        threading.Thread(target=self._fetch_navs_thread, daemon=True).start()

    def _fetch_navs_thread(self):
        transacciones = listar_transacciones()
        if not transacciones:
            return
        isins_unicos = list({t["isin"] for t in transacciones})
        nav_cache = {}
        with ThreadPoolExecutor(max_workers=10) as executor:
            futuros = {executor.submit(obtener_precio_actual, isin): isin for isin in isins_unicos}
            for futuro in as_completed(futuros):
                isin = futuros[futuro]
                try:
                    nav_cache[isin] = futuro.result()
                except Exception:
                    nav_cache[isin] = None
        tc = self._obtener_tc()
        self.after(0, self._actualizar_con_navs, transacciones, nav_cache, tc)

    def _actualizar_con_navs(self, transacciones, nav_cache, tc):
        for row in self.tree_inversiones.get_children():
            self.tree_inversiones.delete(row)

        total_inv_eur = 0
        total_val_eur = 0

        for t in transacciones:
            isin = t["isin"]
            nav_act = nav_cache.get(isin)
            precio_compra = t["precio"]
            part = t["participaciones"]
            moneda = t.get("moneda", "USD")

            precio_compra_eur = convertir_a_eur(precio_compra, moneda, tc)
            nav_act_eur = convertir_a_eur(nav_act, moneda, tc) if nav_act else None

            if nav_act_eur and precio_compra_eur:
                diff_eur = round(nav_act_eur - precio_compra_eur, 2)
                diff_pct = round((diff_eur / precio_compra_eur) * 100, 2) if precio_compra_eur else 0
                cambio_str = f"€{diff_eur:+.2f}"
                val_act_eur = round(part * nav_act_eur, 2)
                cambio_str += f" ({diff_pct:+.2f}%)"
            else:
                cambio_str = "---"
                val_act_eur = None

            total_inv_eur += convertir_a_eur(t["total"], moneda, tc) or 0
            if val_act_eur is not None:
                total_val_eur += val_act_eur

            self.tree_inversiones.insert("", "end", values=(
                t["id"], t["fecha"], isin, t["nombre"][:35], t["tipo"],
                f"{part:.4f}", formatear(precio_compra_eur), formatear(nav_act_eur),
                cambio_str, formatear(convertir_a_eur(t["total"], moneda, tc)),
                formatear(val_act_eur) if val_act_eur else "---",
            ))

        if total_val_eur > 0:
            gan_eur = round(total_val_eur - total_inv_eur, 2)
            gan_pct = round((gan_eur / total_inv_eur) * 100, 2) if total_inv_eur else 0
            self.lbl_resumen_inv.configure(
                text=f"Total invertido: {formatear(total_inv_eur)}  |  "
                     f"Valor actual: {formatear(total_val_eur)}  |  "
                     f"Ganancia/Perdida Total: {formatear(gan_eur)} ({gan_pct:+.2f}%)"
            )
        else:
            self.lbl_resumen_inv.configure(text=f"Total invertido: {formatear(total_inv_eur)}")
        self.set_status("Inversiones actualizadas en EUR.")
        sel = self.tree_inversiones.selection()
        if sel:
            self._on_inversion_select(None)

    def _eliminar_transaccion(self):
        sel = self.tree_inversiones.selection()
        if not sel:
            messagebox.showwarning("Aviso", "Selecciona una transacción primero.")
            return
        item = self.tree_inversiones.item(sel[0])
        trans_id = item["values"][0]
        if messagebox.askyesno("Confirmar", f"¿Eliminar la transacción #{trans_id}?"):
            eliminar_transaccion(trans_id)
            self.set_status(f"Transacción #{trans_id} eliminada.")
            self._cargar_inversiones_inicial()
            self._refrescar_inversiones_background()
            self.detalle_frame.grid_remove()

    def _on_inversion_select(self, event):
        sel = self.tree_inversiones.selection()
        if not sel:
            self.detalle_frame.grid_remove()
            return
        item = self.tree_inversiones.item(sel[0])
        vals = item["values"]
        isin = vals[2]
        threading.Thread(target=self._cargar_detalle, args=(isin,), daemon=True).start()

    def _cargar_detalle(self, isin):
        resumen = obtener_resumen_isin(isin)
        if not resumen:
            self.after(0, self.detalle_frame.grid_remove)
            return
        pos = resumen[0]
        participaciones = pos["total_participaciones"]
        total_invertido = pos["total_invertido"]
        moneda = pos.get("moneda", "USD")
        tc = self._obtener_tc()
        inv_eur = convertir_a_eur(total_invertido, moneda, tc)
        info = obtener_info_fondo(isin)
        nombre = info.get("nombre", isin)
        precio_actual = info.get("precio_actual")
        val_actual_eur = convertir_a_eur(precio_actual * participaciones, moneda, tc) if precio_actual else None
        if val_actual_eur and inv_eur:
            gan_eur = round(val_actual_eur - inv_eur, 2)
            gan_pct = round((gan_eur / inv_eur) * 100, 2)
            gan_line = f"Ganancia: €{gan_eur:+.2f} ({gan_pct:+.2f}%)"
            gan_color = "green" if gan_eur >= 0 else "red"
        else:
            gan_line = "Ganancia: ---"
            gan_color = "white"

        lines = (
            f"FONDO: {nombre}\n"
            f"ISIN: {isin}\n"
            f"Participaciones: {participaciones:.4f}\n"
            f"Invertido: €{inv_eur:,.2f}\n"
            f"Valor actual: {formatear(val_actual_eur)}\n"
            f"{gan_line}\n"
        )

        df = obtener_datos_historicos(isin)
        archivo = None
        if df is not None and not df.empty and len(df) >= 2:
            archivo = generar_grafico_evolucion(df, participaciones, total_invertido, isin, nombre)

        self.after(0, self._mostrar_detalle, lines, archivo)

    def _mostrar_detalle(self, texto, archivo=None):
        self.detalle_texto.delete("0.0", "end")
        self.detalle_texto.insert("0.0", texto)
        if archivo and os.path.exists(archivo):
            try:
                pil_img = Image.open(archivo)
                ctk_img = ctk.CTkImage(light_image=pil_img, dark_image=pil_img, size=(550, 250))
                self.detalle_img.configure(image=ctk_img, text="")
                self.detalle_img.image = ctk_img
            except Exception:
                self.detalle_img.configure(text="Error al cargar imagen", image="")
        else:
            self.detalle_img.configure(text="No hay suficientes datos\npara generar el gráfico", font=("Segoe UI", 12))
        self.detalle_frame.grid()

    def _build_tab_rendimiento(self):
        self.tab_rendimiento.grid_rowconfigure(0, weight=0)
        self.tab_rendimiento.grid_rowconfigure(1, weight=1)
        self.tab_rendimiento.grid_columnconfigure(0, weight=1)

        cols = ("isin", "nombre", "part", "invertido", "valor_actual", "ganancia")
        self.tree_rendimiento = ttk.Treeview(self.tab_rendimiento, columns=cols, show="headings", height=8)
        headings = [
            ("isin", "ISIN", 130),
            ("nombre", "Nombre", 220),
            ("part", "Participaciones", 110),
            ("invertido", "Total Invertido", 130),
            ("valor_actual", "Valor Actual", 130),
            ("ganancia", "Ganancia/Pérdida", 160),
        ]
        for col, text, width in headings:
            self.tree_rendimiento.heading(col, text=text)
            self.tree_rendimiento.column(col, width=width, anchor="center" if col != "nombre" else "w")

        vsb = ttk.Scrollbar(self.tab_rendimiento, orient="vertical", command=self.tree_rendimiento.yview)
        self.tree_rendimiento.configure(yscrollcommand=vsb.set)
        self.tree_rendimiento.grid(row=0, column=0, sticky="nsew", padx=10, pady=(10, 2))
        vsb.grid(row=0, column=0, sticky="nse", padx=(0, 10), pady=(10, 2))

        self.lbl_rend_img = ctk.CTkLabel(
            self.tab_rendimiento, text="Haz doble clic en una inversión\npara ver su evolución",
            anchor="center", font=("Segoe UI", 13), fg_color="#1a1a1a"
        )
        self.lbl_rend_img.grid(row=1, column=0, sticky="nsew", padx=10, pady=(2, 10))

        self.tree_rendimiento.bind("<Double-1>", self._on_rendimiento_doble_click)
        self._cargar_lista_rendimientos()

    def _cargar_lista_rendimientos(self):
        for row in self.tree_rendimiento.get_children():
            self.tree_rendimiento.delete(row)
        portfolio = obtener_portfolio()
        if not portfolio:
            self.lbl_rend_img.configure(text="No hay transacciones.\nAgrega una desde la pestaña 'Agregar'.")
            return
        self.lbl_rend_img.configure(text="Cargando valores actuales...")
        threading.Thread(target=self._fetch_rendimientos, args=(portfolio,), daemon=True).start()

    def _fetch_rendimientos(self, portfolio):
        isins = [p["isin"] for p in portfolio]
        nav_cache = {}
        with ThreadPoolExecutor(max_workers=10) as executor:
            futuros = {executor.submit(obtener_precio_actual, isin): isin for isin in isins}
            for futuro in as_completed(futuros):
                isin = futuros[futuro]
                try:
                    nav_cache[isin] = futuro.result()
                except Exception:
                    nav_cache[isin] = None
        tc = self._obtener_tc()

        def form(valor, moneda="USD"):
            if valor is None:
                return "---"
            eur = convertir_a_eur(valor, moneda, tc)
            return f"€{eur:,.2f}" if eur else f"${valor:,.2f}"

        rows = []
        for p in portfolio:
            isin = p["isin"]
            nombre = p["nombre"][:40]
            part = p["total_participaciones"]
            inv = p["total_invertido"]
            moneda = p.get("moneda", "USD")
            nav = nav_cache.get(isin)
            val_act = round(part * nav, 2) if nav and part else None
            if val_act and inv:
                gan = round(val_act - inv, 2)
                gan_pct = round((gan / inv) * 100, 2) if inv else 0
                gan_str = f"{form(gan, moneda)} ({gan_pct:+.2f}%)"
            else:
                gan_str = "---"
            rows.append((isin, nombre, f"{part:.4f}", form(inv, moneda), form(val_act, moneda) if val_act else "---", gan_str))

        self.after(0, self._mostrar_lista_rendimientos, rows)

    def _mostrar_lista_rendimientos(self, rows):
        for row in self.tree_rendimiento.get_children():
            self.tree_rendimiento.delete(row)
        for vals in rows:
            self.tree_rendimiento.insert("", "end", values=vals)
        self.lbl_rend_img.configure(text="Haz doble clic en una inversión\npara ver su evolución")

    def _on_rendimiento_doble_click(self, event):
        sel = self.tree_rendimiento.selection()
        if not sel:
            return
        item = self.tree_rendimiento.item(sel[0])
        vals = item["values"]
        isin = vals[0]
        self.lbl_rend_img.configure(text="Cargando gráfico...")
        threading.Thread(target=self._cargar_grafico_rend, args=(isin,), daemon=True).start()

    def _cargar_grafico_rend(self, isin):
        if isin in self._info_fondo_cache:
            info = self._info_fondo_cache[isin]
        else:
            info = obtener_info_fondo(isin)
            self._info_fondo_cache[isin] = info

        nombre = info.get("nombre", isin)
        df = obtener_datos_historicos(isin)
        if df is None or df.empty or len(df) < 5:
            self.after(0, lambda: self.lbl_rend_img.configure(
                text="No hay suficientes datos históricos\npara generar el gráfico"))
            return
        resumen = obtener_resumen_isin(isin)
        if not resumen:
            self.after(0, lambda: self.lbl_rend_img.configure(text="No hay transacciones para este ISIN."))
            return
        pos = resumen[0]
        participaciones = pos["total_participaciones"]
        total_invertido = pos["total_invertido"]
        archivo = generar_grafico_pnl_linea(df, participaciones, total_invertido, isin, nombre)
        self.after(0, self._mostrar_grafico_rend, archivo, isin)

    def _mostrar_grafico_rend(self, archivo, isin):
        if archivo and os.path.exists(archivo):
            try:
                pil_img = Image.open(archivo)
                ctk_img = ctk.CTkImage(light_image=pil_img, dark_image=pil_img, size=(700, 350))
                self.lbl_rend_img.configure(image=ctk_img, text="")
                self.lbl_rend_img.image = ctk_img
                self.set_status(f"Gráfico P&L generado para {isin}.")
            except Exception as e:
                self.lbl_rend_img.configure(text=f"Error al mostrar imagen: {e}")
        else:
            self.lbl_rend_img.configure(text="No se pudo generar el gráfico\n(datos insuficientes)")


if __name__ == "__main__":
    app = App()
    app.mainloop()
