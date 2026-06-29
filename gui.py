import customtkinter as ctk
from tkinter import ttk, messagebox
from datetime import datetime
import threading
import os
import numpy as np
import pandas as pd
from matplotlib.backends.backend_tkagg import FigureCanvasTkAgg, NavigationToolbar2Tk
import matplotlib.pyplot as plt

from database import (
    init_db, agregar_transaccion, listar_transacciones,
    eliminar_transaccion, actualizar_transaccion,
    obtener_portfolio,
    obtener_estado_transacciones, guardar_rendimiento_cache, cargar_rendimiento_cache,
)
from fondos import (
    obtener_info_fondo, obtener_precio_actual, obtener_precio_historico_en_fecha,
    obtener_tipo_cambio, convertir_a_eur, calcular_serie_rendimiento
)
from concurrent.futures import ThreadPoolExecutor, as_completed

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
            self._cargar_rendimiento_gui()

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
        self.tree_inversiones = ttk.Treeview(frame, columns=cols, show="tree headings", height=12)
        self.tree_inversiones.tag_configure("parent", font=("Segoe UI", 11, "bold"))
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

        self.tree_inversiones.bind("<Double-1>", self._editar_transaccion)

        btn_frame = ctk.CTkFrame(self.tab_inversiones, fg_color="transparent")
        btn_frame.grid(row=1, column=0, sticky="ew", padx=10, pady=(0, 5))
        ctk.CTkButton(btn_frame, text="Actualizar NAVs", command=self._refrescar_inversiones_background).pack(side="left", padx=5)
        ctk.CTkButton(btn_frame, text="Eliminar Seleccionada", command=self._eliminar_transaccion).pack(side="right", padx=5)

        self.lbl_resumen_inv = ctk.CTkLabel(self.tab_inversiones, text="", font=("Segoe UI", 14, "bold"))
        self.lbl_resumen_inv.grid(row=2, column=0, sticky="ew", padx=15, pady=(0, 5))

        self._cargar_inversiones_inicial()
        self.after(200, self._refrescar_inversiones_background)

    def _agrupar_por_isin(self, transacciones):
        grupos = {}
        for t in transacciones:
            isin = t["isin"]
            if isin not in grupos:
                grupos[isin] = {"transacciones": [], "nombre": t["nombre"]}
            grupos[isin]["transacciones"].append(t)
        return grupos

    def _cargar_inversiones_inicial(self):
        for row in self.tree_inversiones.get_children():
            self.tree_inversiones.delete(row)
        transacciones = listar_transacciones()
        if not transacciones:
            self.lbl_resumen_inv.configure(text="No hay transacciones. Agrega una en la pestaña 'Agregar'.")
            return
        tc = self._obtener_tc()
        total_inv_eur = 0
        grupos = self._agrupar_por_isin(transacciones)
        for isin, grupo in grupos.items():
            trans = grupo["transacciones"]
            nombre = grupo["nombre"]
            total_part = 0
            total_inv = 0.0
            for t in trans:
                part = t["participaciones"]
                if t["tipo"] == "compra":
                    total_part += part
                    total_inv += t["total"]
                else:
                    total_part -= part
                    total_inv -= t["total"]
            if total_part <= 0:
                continue
            moneda = trans[0].get("moneda", "USD")
            total_inv_eur_isin = convertir_a_eur(total_inv, moneda, tc) or 0
            total_inv_eur += total_inv_eur_isin
            parent_id = f"isin_{isin}"
            self.tree_inversiones.insert("", "end", iid=parent_id, open=True, tags=("parent",), values=(
                "", "", isin, nombre[:35], "",
                f"{total_part:.4f}", "---", "---", "---",
                formatear(total_inv_eur_isin), "---",
            ))
            for t in trans:
                moneda_t = t.get("moneda", "USD")
                part_t = t["participaciones"]
                precio_eur = convertir_a_eur(t["precio"], moneda_t, tc)
                total_eur = convertir_a_eur(t["total"], moneda_t, tc)
                self.tree_inversiones.insert(parent_id, "end", iid=str(t["id"]), values=(
                    t["id"], t["fecha"], isin, t["nombre"][:35], t["tipo"],
                    f"{part_t:.4f}", formatear(precio_eur), "---", "---",
                    formatear(total_eur), "---",
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
        grupos = self._agrupar_por_isin(transacciones)

        for isin, grupo in grupos.items():
            trans = grupo["transacciones"]
            nombre = grupo["nombre"]
            nav_act = nav_cache.get(isin)
            total_part = 0
            total_inv = 0.0

            for t in trans:
                part = t["participaciones"]
                if t["tipo"] == "compra":
                    total_part += part
                    total_inv += t["total"]
                else:
                    total_part -= part
                    total_inv -= t["total"]

            if total_part <= 0:
                continue

            moneda = trans[0].get("moneda", "USD")
            nav_act_eur = convertir_a_eur(nav_act, moneda, tc) if nav_act else None
            total_inv_eur_isin = convertir_a_eur(total_inv, moneda, tc) or 0
            total_inv_eur += total_inv_eur_isin

            if nav_act_eur and total_inv_eur_isin:
                val_act_eur = round(total_part * nav_act_eur, 2)
                diff_eur = round(val_act_eur - total_inv_eur_isin, 2)
                diff_pct = round((diff_eur / total_inv_eur_isin) * 100, 2) if total_inv_eur_isin else 0
                cambio_str = f"€{diff_eur:+.2f} ({diff_pct:+.2f}%)"
                total_val_eur += val_act_eur
            else:
                cambio_str = "---"
                val_act_eur = None

            parent_id = f"isin_{isin}"
            self.tree_inversiones.insert("", "end", iid=parent_id, open=True, tags=("parent",), values=(
                "", "", isin, nombre[:35], "",
                f"{total_part:.4f}", "---", formatear(nav_act_eur),
                cambio_str, formatear(total_inv_eur_isin),
                formatear(val_act_eur) if val_act_eur else "---",
            ))

            for t in trans:
                moneda_t = t.get("moneda", "USD")
                precio_compra = t["precio"]
                part_t = t["participaciones"]
                precio_compra_eur = convertir_a_eur(precio_compra, moneda_t, tc)
                nav_act_eur_t = convertir_a_eur(nav_act, moneda_t, tc) if nav_act else None

                if nav_act_eur_t and precio_compra_eur:
                    diff_eur_t = round(nav_act_eur_t - precio_compra_eur, 2)
                    diff_pct_t = round((diff_eur_t / precio_compra_eur) * 100, 2) if precio_compra_eur else 0
                    cambio_str_t = f"€{diff_eur_t:+.2f} ({diff_pct_t:+.2f}%)"
                    val_act_eur_t = round(part_t * nav_act_eur_t, 2)
                else:
                    cambio_str_t = "---"
                    val_act_eur_t = None

                self.tree_inversiones.insert(parent_id, "end", iid=str(t["id"]), values=(
                    t["id"], t["fecha"], isin, t["nombre"][:35], t["tipo"],
                    f"{part_t:.4f}", formatear(precio_compra_eur), formatear(nav_act_eur_t),
                    cambio_str_t, formatear(convertir_a_eur(t["total"], moneda_t, tc)),
                    formatear(val_act_eur_t) if val_act_eur_t else "---",
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
        item_id = sel[0]
        if item_id.startswith("isin_"):
            messagebox.showwarning("Aviso", "Selecciona una transacción individual dentro del grupo (expande con la flecha).")
            return
        trans_id = int(item_id)
        if messagebox.askyesno("Confirmar", f"¿Eliminar la transacción #{trans_id}?"):
            eliminar_transaccion(trans_id)
            self.set_status(f"Transacción #{trans_id} eliminada.")
            self._cargar_inversiones_inicial()
            self._refrescar_inversiones_background()



    def _editar_transaccion(self, event):
        sel = self.tree_inversiones.selection()
        if not sel:
            return
        item_id = sel[0]
        if item_id.startswith("isin_"):
            return
        trans_id = int(item_id)

        transacciones = listar_transacciones()
        t = next((t for t in transacciones if t["id"] == trans_id), None)
        if not t:
            return

        dialog = ctk.CTkToplevel(self)
        dialog.title(f"Editar Transacción #{trans_id}")
        dialog.geometry("420x350")
        dialog.resizable(False, False)
        dialog.transient(self)
        dialog.grab_set()

        frame = ctk.CTkFrame(dialog, fg_color="transparent")
        frame.pack(fill="both", expand=True, padx=15, pady=15)

        campos = [
            ("ID", f"#{trans_id}"),
            ("ISIN", t["isin"]),
            ("Nombre", t["nombre"][:50]),
        ]
        for i, (label, val) in enumerate(campos):
            ctk.CTkLabel(frame, text=label, font=("Segoe UI", 12, "bold")).grid(row=i, column=0, sticky="w", pady=2)
            ctk.CTkLabel(frame, text=val, font=("Consolas", 12), text_color="lightblue").grid(row=i, column=1, sticky="w", pady=2)

        row = len(campos)
        ctk.CTkLabel(frame, text="Fecha", font=("Segoe UI", 12, "bold")).grid(row=row, column=0, sticky="w", pady=2)
        fecha_entry = ctk.CTkEntry(frame, placeholder_text="YYYY-MM-DD")
        fecha_entry.insert(0, t["fecha"])
        fecha_entry.grid(row=row, column=1, sticky="ew", pady=2)

        row += 1
        ctk.CTkLabel(frame, text="Tipo", font=("Segoe UI", 12, "bold")).grid(row=row, column=0, sticky="w", pady=2)
        tipo_combo = ctk.CTkComboBox(frame, values=["compra", "venta"], state="readonly")
        tipo_combo.set(t["tipo"])
        tipo_combo.grid(row=row, column=1, sticky="ew", pady=2)

        row += 1
        ctk.CTkLabel(frame, text="Participaciones", font=("Segoe UI", 12, "bold")).grid(row=row, column=0, sticky="w", pady=2)
        part_entry = ctk.CTkEntry(frame)
        part_entry.insert(0, str(t["participaciones"]))
        part_entry.grid(row=row, column=1, sticky="ew", pady=2)

        row += 1
        ctk.CTkLabel(frame, text="Precio (NAV)", font=("Segoe UI", 12, "bold")).grid(row=row, column=0, sticky="w", pady=2)
        precio_entry = ctk.CTkEntry(frame)
        precio_entry.insert(0, str(t["precio"]))
        precio_entry.grid(row=row, column=1, sticky="ew", pady=2)

        row += 1
        ctk.CTkLabel(frame, text="Moneda", font=("Segoe UI", 12, "bold")).grid(row=row, column=0, sticky="w", pady=2)
        moneda_entry = ctk.CTkEntry(frame)
        moneda_entry.insert(0, t.get("moneda", "USD"))
        moneda_entry.grid(row=row, column=1, sticky="ew", pady=2)

        row += 1
        btn_frame = ctk.CTkFrame(frame, fg_color="transparent")
        btn_frame.grid(row=row, column=0, columnspan=2, pady=(12, 0))
        ctk.CTkButton(btn_frame, text="Guardar", command=lambda: self._guardar_edicion(
            dialog, trans_id, fecha_entry, tipo_combo, part_entry, precio_entry, moneda_entry
        )).pack(side="left", padx=5)
        ctk.CTkButton(btn_frame, text="Cancelar", command=dialog.destroy, fg_color="#555555",
                      hover_color="#777777").pack(side="left", padx=5)

        frame.grid_columnconfigure(1, weight=1)

    def _guardar_edicion(self, dialog, trans_id, fecha_entry, tipo_combo, part_entry, precio_entry, moneda_entry):
        try:
            fecha = fecha_entry.get().strip()
            datetime.strptime(fecha, "%Y-%m-%d")
        except (ValueError, AttributeError):
            messagebox.showwarning("Error", "Fecha inválida. Usa YYYY-MM-DD.", parent=dialog)
            return
        tipo = tipo_combo.get()
        try:
            participaciones = float(part_entry.get().strip())
            precio = float(precio_entry.get().strip())
            if participaciones <= 0 or precio <= 0:
                raise ValueError
        except (ValueError, AttributeError):
            messagebox.showwarning("Error", "Participaciones y precio deben ser números positivos.", parent=dialog)
            return
        moneda = moneda_entry.get().strip().upper()
        if moneda not in ("USD", "EUR", "GBP", "CHF", "JPY", "CAD", "AUD", "SEK", "NOK", "DKK", "PLN", "HKD", "SGD"):
            messagebox.showwarning("Error", f"Moneda no reconocida: {moneda}", parent=dialog)
            return

        total = round(participaciones * precio, 2)

        ok = actualizar_transaccion(trans_id, fecha, tipo, participaciones, precio, total, moneda)
        if ok:
            dialog.destroy()
            self.set_status(f"Transacción #{trans_id} actualizada.")
            self._cargar_inversiones_inicial()
            self._refrescar_inversiones_background()
        else:
            messagebox.showerror("Error", "No se pudo actualizar la transacción.", parent=dialog)

    def _build_tab_historial(self):
        self.tab_historial.grid_rowconfigure(1, weight=0)
        self.tab_historial.grid_rowconfigure(2, weight=1)
        self.tab_historial.grid_columnconfigure(0, weight=1)

        btn_frame = ctk.CTkFrame(self.tab_historial, fg_color="transparent")
        btn_frame.grid(row=0, column=0, sticky="ew", padx=10, pady=(10, 5))
        self.btn_recalcular_rend = ctk.CTkButton(
            btn_frame, text="Recalcular",
            command=self._recalcular_rendimiento_gui
        )
        self.btn_recalcular_rend.pack(side="left", padx=5)
        self.lbl_rend_status = ctk.CTkLabel(btn_frame, text="", font=("Segoe UI", 12))
        self.lbl_rend_status.pack(side="left", padx=10)

        self.rend_canvas_frame = ctk.CTkFrame(self.tab_historial, fg_color="#1a1a1a")
        self.rend_canvas_frame.grid(row=2, column=0, sticky="nsew", padx=10, pady=(0, 10))

        self.rend_canvas = None
        self.rend_toolbar = None
        self.rend_no_data_label = ctk.CTkLabel(
            self.rend_canvas_frame,
            text="Agrega transacciones para ver\nel rendimiento histórico",
            anchor="center", font=("Segoe UI", 13)
        )
        self.rend_no_data_label.pack(fill="both", expand=True)

        self.after(200, self._cargar_rendimiento_gui)

    def _destruir_canvas_rend(self):
        if self.rend_canvas:
            self.rend_canvas.get_tk_widget().destroy()
            self.rend_canvas = None
        if self.rend_toolbar:
            self.rend_toolbar.destroy()
            self.rend_toolbar = None

    def _mostrar_no_data_rend(self, texto="Agrega transacciones para ver\nel rendimiento histórico"):
        self._destruir_canvas_rend()
        self.rend_no_data_label.configure(text=texto)
        self.rend_no_data_label.pack(fill="both", expand=True)
        self.rend_no_data_label.lift()

    def _recalcular_rendimiento_gui(self):
        self.btn_recalcular_rend.configure(state="disabled", text="Calculando...")
        self.lbl_rend_status.configure(text="Obteniendo datos históricos...")
        threading.Thread(target=self._task_calcular_rendimiento, daemon=True).start()

    def _cargar_rendimiento_gui(self):
        transacciones = listar_transacciones()
        if not transacciones:
            self._mostrar_no_data_rend()
            return

        estado_hash = obtener_estado_transacciones()
        cached = cargar_rendimiento_cache(estado_hash)
        if cached is not None:
            import json
            data = json.loads(cached)
            if data and len(data.get("fechas", [])) >= 2:
                self._dibujar_grafico_rend(data)
                self.lbl_rend_status.configure(text="Rendimiento cargado (en caché)", text_color="green")
                return

        self._recalcular_rendimiento_gui()

    def _task_calcular_rendimiento(self):
        try:
            tc = self._obtener_tc()
            transacciones = listar_transacciones()
            rends = calcular_serie_rendimiento(transacciones, paso_dias=5, tc=tc)

            if rends is not None and len(rends["return_pct"]) >= 2:
                import json
                data = {
                    "fechas": [str(f)[:10] for f in rends["fechas"]],
                    "return_pct": [round(float(x), 4) for x in rends["return_pct"]],
                }
                estado_hash = obtener_estado_transacciones()
                guardar_rendimiento_cache(estado_hash, json.dumps(data))
                self.after(0, lambda: self._completar_rendimiento_gui(data, None))
            else:
                self.after(0, lambda: self._completar_rendimiento_gui(None,
                            "No hay suficientes datos con NAV histórico para calcular rendimientos."))
        except Exception as e:
            self.after(0, lambda: self._completar_rendimiento_gui(None, f"Error: {e}"))

    def _completar_rendimiento_gui(self, data, error_msg):
        self.btn_recalcular_rend.configure(state="normal", text="Recalcular")
        if error_msg:
            self.lbl_rend_status.configure(text=error_msg, text_color="red")
            self._mostrar_no_data_rend(error_msg)
            return
        if data and len(data["fechas"]) >= 2:
            self.lbl_rend_status.configure(text=f"Rendimiento calculado ({len(data['fechas'])} muestras)", text_color="green")
            self._dibujar_grafico_rend(data)
        else:
            self.lbl_rend_status.configure(text="Datos insuficientes", text_color="orange")
            self._mostrar_no_data_rend("No hay suficientes datos para graficar.")

    def _dibujar_grafico_rend(self, data):
        self._destruir_canvas_rend()

        try:
            fechas = [pd.Timestamp(f) for f in data["fechas"]]
            returns = data["return_pct"]

            fig = plt.Figure()
            fig.patch.set_facecolor('#1a1a1a')
            fig.set_size_inches(9, 4, forward=True)
            ax = fig.add_subplot(111)
            ax.set_facecolor('#1a1a1a')
            ax.spines['bottom'].set_color('#555555')
            ax.spines['left'].set_color('#555555')
            ax.spines['top'].set_visible(False)
            ax.spines['right'].set_visible(False)
            ax.tick_params(colors='#cccccc', labelsize=8)

            ax.plot(fechas, returns, color="#2e7d32", linewidth=1.8, marker="o", markersize=3)
            ax.axhline(0, color="#888888", linewidth=0.8, linestyle="--")

            ax.set_xlabel("Fecha", fontsize=10, color="#cccccc")
            ax.set_ylabel("Rendimiento (%)", fontsize=10, color="#cccccc")
            ax.set_title("Rendimiento del Portafolio sobre Capital Invertido",
                         fontsize=12, fontweight="bold", color="#ffffff")

            last_ret = returns[-1]
            color_ret = "#2e7d32" if last_ret >= 0 else "#d32f2f"
            ax.annotate(f"{last_ret:+.2f}%", xy=(fechas[-1], last_ret),
                        xytext=(5, 0), textcoords="offset points",
                        fontsize=9, fontweight="bold", color=color_ret)

            fig.autofmt_xdate()
            fig.tight_layout()

            self.rend_no_data_label.pack_forget()

            self.rend_canvas = FigureCanvasTkAgg(fig, master=self.rend_canvas_frame)
            self.rend_canvas.draw()
            self.rend_canvas.get_tk_widget().pack(fill="both", expand=True)

            self.rend_toolbar = NavigationToolbar2Tk(self.rend_canvas, self.rend_canvas_frame)
            self.rend_toolbar.update()
        except Exception as e:
            self._mostrar_no_data_rend(f"Error al generar gráfico:\n{e}")


if __name__ == "__main__":
    app = App()
    app.mainloop()
