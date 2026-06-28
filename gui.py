import customtkinter as ctk
from tkinter import ttk, messagebox
from datetime import datetime
import threading
import os
from matplotlib.backends.backend_tkagg import FigureCanvasTkAgg, NavigationToolbar2Tk
import matplotlib.pyplot as plt

from database import (
    init_db, agregar_transaccion, listar_transacciones,
    eliminar_transaccion, eliminar_snapshot, obtener_portfolio,
    obtener_snapshots, obtener_snapshots_asc,
)
from fondos import (
    obtener_info_fondo, obtener_precio_actual, obtener_precio_historico_en_fecha,
    obtener_tipo_cambio, convertir_a_eur
)
from concurrent.futures import ThreadPoolExecutor, as_completed
from snapshot import tomar_snapshot

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
        self.tab_historial = self.tabview.add("Historial")

        self._build_tab_agregar()
        self._build_tab_inversiones()
        self._build_tab_historial()

    def _on_tab_change(self, tab_name):
        if tab_name == "Historial":
            self._cargar_snapshots_gui()

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
        moneda = info.get("moneda", "USD")
        total_eur = convertir_a_eur(info.get("total", 0), moneda, tc)
        if total_eur:
            fila(5, "Total estimado:", f"€{total_eur:,.2f}")
        else:
            fila(5, "Total estimado:", f"{info.get('total', 0):,.2f} {moneda}")

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
        moneda = info.get("moneda", "USD")
        nav = nav_hist if nav_hist is not None else info.get("precio_actual")

        total = round(participaciones * nav, 2) if nav else 0
        tc = self._obtener_tc()
        nav_eur = convertir_a_eur(nav, moneda, tc) if nav else None
        nav_str = f"€{nav_eur:,.4f}" if nav_eur else "---"

        self.after(0, lambda: self._completar_preview(
            isin, ticker, nombre, moneda, nav, nav_str, total, fecha, participaciones
        ))

    def _completar_preview(self, isin, ticker, nombre, moneda, nav, nav_str, total, fecha, participaciones):
        self._mostrar_preview({
            "isin": isin, "ticker": ticker, "nombre": nombre,
            "moneda": moneda, "nav": nav, "nav_str": nav_str,
            "total": total, "fecha": fecha, "participaciones": participaciones,
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

        moneda = info.get("moneda", "USD")
        trans_id = agregar_transaccion(isin, nombre, tipo, participaciones, precio, total, fecha, moneda=moneda, ticker=ticker)

        tc = self._obtener_tc()
        total_eur = convertir_a_eur(total, moneda, tc)
        self.set_status(f"Transacción #{trans_id} registrada: {tipo} de {participaciones} {isin}")
        if total_eur is not None:
            messagebox.showinfo("OK", f"Transacción registrada (ID: {trans_id})\nTotal: €{total_eur:,.2f}")
        else:
            messagebox.showinfo("OK", f"Transacción registrada (ID: {trans_id})\nTotal: {total:,.2f} {moneda}")

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



    def _build_tab_historial(self):
        self.tab_historial.grid_rowconfigure(1, weight=0)
        self.tab_historial.grid_rowconfigure(2, weight=1)
        self.tab_historial.grid_columnconfigure(0, weight=1)

        btn_frame = ctk.CTkFrame(self.tab_historial, fg_color="transparent")
        btn_frame.grid(row=0, column=0, sticky="ew", padx=10, pady=(10, 5))
        self.btn_tomar_snapshot = ctk.CTkButton(
            btn_frame, text="Tomar Snapshot Ahora",
            command=self._tomar_snapshot_gui
        )
        self.btn_tomar_snapshot.pack(side="left", padx=5)
        self.btn_eliminar_snapshot = ctk.CTkButton(
            btn_frame, text="Eliminar Snapshot",
            command=self._eliminar_snapshot_gui, fg_color="#b71c1c",
            hover_color="#d32f2f"
        )
        self.btn_eliminar_snapshot.pack(side="right", padx=5)
        self.lbl_snap_status = ctk.CTkLabel(btn_frame, text="", font=("Segoe UI", 12))
        self.lbl_snap_status.pack(side="left", padx=10)

        frame = ctk.CTkFrame(self.tab_historial)
        frame.grid(row=1, column=0, sticky="nsew", padx=10, pady=5)
        frame.grid_rowconfigure(0, weight=1)
        frame.grid_columnconfigure(0, weight=1)

        cols = ("fecha", "invertido", "valor", "daily_pnl", "cum_pnl")
        self.tree_snapshots = ttk.Treeview(frame, columns=cols, show="headings", height=6)
        headings = [
            ("fecha", "Fecha", 150),
            ("invertido", "Invertido", 120),
            ("valor", "Valor Actual", 120),
            ("daily_pnl", "P&L Diario", 120),
            ("cum_pnl", "P&L Acumulado", 140),
        ]
        for col, text, width in headings:
            self.tree_snapshots.heading(col, text=text)
            self.tree_snapshots.column(col, width=width, anchor="center")

        vsb = ttk.Scrollbar(frame, orient="vertical", command=self.tree_snapshots.yview)
        self.tree_snapshots.configure(yscrollcommand=vsb.set)
        self.tree_snapshots.grid(row=0, column=0, sticky="nsew")
        vsb.grid(row=0, column=1, sticky="ns")

        self.snap_canvas_frame = ctk.CTkFrame(self.tab_historial, fg_color="#1a1a1a")
        self.snap_canvas_frame.grid(row=2, column=0, sticky="nsew", padx=10, pady=(0, 10))

        self.snap_canvas = None
        self.snap_toolbar = None
        self.snap_no_data_label = ctk.CTkLabel(
            self.snap_canvas_frame,
            text="Toma un snapshot para comenzar\nel historial de evolución",
            anchor="center", font=("Segoe UI", 13)
        )
        self.snap_no_data_label.pack(fill="both", expand=True)

        self.after(200, self._cargar_snapshots_gui)

    def _tomar_snapshot_gui(self):
        self.btn_tomar_snapshot.configure(state="disabled", text="Calculando...")
        self.lbl_snap_status.configure(text="Obteniendo precios...")
        threading.Thread(target=self._task_tomar_snapshot, daemon=True).start()

    def _task_tomar_snapshot(self):
        try:
            resultado = tomar_snapshot()
            dpnl_str = f"{resultado['daily_pnl']:+.2f}" if resultado['daily_pnl'] is not None else "N/A"
            msg = (f"Snapshot {resultado['fecha']}: "
                   f"EUR {resultado['total_valor']:,.2f} | "
                   f"P&L diario: EUR {dpnl_str} | "
                   f"P&L acum.: EUR {resultado['cumulative_pnl']:+,.2f}")
            self.after(0, lambda: self._completar_snapshot_gui(msg))
        except Exception as e:
            self.after(0, lambda: self._completar_snapshot_gui(f"Error: {e}", error=True))

    def _completar_snapshot_gui(self, msg, error=False):
        self.btn_tomar_snapshot.configure(state="normal", text="Tomar Snapshot Ahora")
        color = "red" if error else "green"
        self.lbl_snap_status.configure(text=msg, text_color=color)
        self._cargar_snapshots_gui()

    def _eliminar_snapshot_gui(self):
        sel = self.tree_snapshots.selection()
        if not sel:
            messagebox.showwarning("Aviso", "Selecciona un snapshot primero.")
            return
        snap_id = int(sel[0])
        fecha = self.tree_snapshots.item(snap_id, "values")[0]
        if messagebox.askyesno("Confirmar", f"¿Eliminar el snapshot del {fecha}?"):
            eliminar_snapshot(snap_id)
            self.set_status(f"Snapshot {fecha} eliminado.")
            self._cargar_snapshots_gui()

    def _destruir_canvas(self):
        if self.snap_canvas:
            self.snap_canvas.get_tk_widget().destroy()
            self.snap_canvas = None
        if self.snap_toolbar:
            self.snap_toolbar.destroy()
            self.snap_toolbar = None

    def _mostrar_no_data(self, texto="Toma un snapshot para comenzar\nel historial de evolución"):
        self._destruir_canvas()
        self.snap_no_data_label.configure(text=texto)
        self.snap_no_data_label.pack(fill="both", expand=True)
        self.snap_no_data_label.lift()

    def _cargar_snapshots_gui(self):
        snapshots = obtener_snapshots_asc()
        for row in self.tree_snapshots.get_children():
            self.tree_snapshots.delete(row)

        if not snapshots:
            self._mostrar_no_data()
            return

        for s in snapshots:
            dpnl = f"EUR {s['daily_pnl']:+.2f}" if s['daily_pnl'] is not None else "---"
            self.tree_snapshots.insert("", "end", iid=str(s["id"]), values=(
                s["fecha"],
                f"EUR {s['total_invertido']:,.2f}",
                f"EUR {s['total_valor']:,.2f}",
                dpnl,
                f"EUR {s['cumulative_pnl']:+,.2f}",
            ))

        self._generar_grafico_snapshots(snapshots)

    def _generar_grafico_snapshots(self, snapshots):
        if len(snapshots) < 2:
            self._mostrar_no_data(
                "Se necesitan al menos 2 snapshots\npara generar el gráfico de evolución"
            )
            return

        try:
            fechas = [s["fecha"] for s in snapshots]
            valores = [s["total_valor"] for s in snapshots]
            invertidos = [s["total_invertido"] for s in snapshots]
            pnls = [s["cumulative_pnl"] for s in snapshots]

            self._destruir_canvas()

            fig, (ax1, ax2) = plt.subplots(2, 1, gridspec_kw={"height_ratios": [2, 1]})
            fig.patch.set_facecolor('#1a1a1a')
            fig.set_size_inches(9, 5, forward=True)

            x = list(range(len(fechas)))
            tick_step = max(1, len(fechas) // 12)
            tick_pos = list(range(0, len(fechas), tick_step))
            if tick_pos[-1] != len(fechas) - 1:
                tick_pos.append(len(fechas) - 1)
            tick_lbl = [str(fechas[i])[:10] for i in tick_pos]

            for ax in (ax1, ax2):
                ax.set_facecolor('#1a1a1a')
                ax.spines['bottom'].set_color('#555555')
                ax.spines['left'].set_color('#555555')
                ax.spines['top'].set_visible(False)
                ax.spines['right'].set_visible(False)
                ax.tick_params(colors='#cccccc', labelsize=8)

            ax1.plot(x, valores, color="#4caf50", linewidth=2, marker="o", markersize=4, label="Valor actual")
            ax1.plot(x, invertidos, color="#ff8f00", linestyle="--", linewidth=1.5, label="Invertido")
            ax1.fill_between(x, invertidos, valores,
                             where=[v >= i for v, i in zip(valores, invertidos)],
                             color="#2e7d32", alpha=0.15)
            ax1.fill_between(x, invertidos, valores,
                             where=[v < i for v, i in zip(valores, invertidos)],
                             color="#d32f2f", alpha=0.15)
            ax1.set_ylabel("EUR", fontsize=10, color="#cccccc")
            ax1.set_title("Evolución del Portafolio", fontsize=12, fontweight="bold", color="#ffffff")
            ax1.legend(fontsize=9, loc="upper left", labelcolor="#cccccc")
            ax1.set_xticks(tick_pos)
            ax1.set_xticklabels(tick_lbl, rotation=45, ha="right", fontsize=7)

            ax2.plot(x, pnls, color="#4caf50", linewidth=1.5, marker="o", markersize=4)
            ax2.fill_between(x, pnls, 0,
                             where=[p >= 0 for p in pnls],
                             color="#2e7d32", alpha=0.3, label="Ganancia")
            ax2.fill_between(x, pnls, 0,
                             where=[p < 0 for p in pnls],
                             color="#d32f2f", alpha=0.3, label="Pérdida")
            ax2.axhline(0, color="#888888", linewidth=0.8)
            ax2.set_ylabel("EUR", fontsize=10, color="#cccccc")
            ax2.set_title("P&L Acumulado", fontsize=12, fontweight="bold", color="#ffffff")
            ax2.legend(fontsize=9, loc="upper left", labelcolor="#cccccc")
            ax2.set_xticks(tick_pos)
            ax2.set_xticklabels(tick_lbl, rotation=45, ha="right", fontsize=7)

            plt.tight_layout()

            self.snap_no_data_label.pack_forget()

            self.snap_canvas = FigureCanvasTkAgg(fig, master=self.snap_canvas_frame)
            self.snap_canvas.draw()
            self.snap_canvas.get_tk_widget().pack(fill="both", expand=True)

            self.snap_toolbar = NavigationToolbar2Tk(self.snap_canvas, self.snap_canvas_frame)
            self.snap_toolbar.update()
        except Exception as e:
            self._mostrar_no_data(f"Error al generar gráfico:\n{e}")


if __name__ == "__main__":
    app = App()
    app.mainloop()
