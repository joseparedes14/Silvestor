import customtkinter as ctk
from tkinter import ttk, messagebox
from datetime import datetime
import threading
import os
from PIL import Image

from database import (
    init_db, agregar_transaccion, listar_transacciones,
    eliminar_transaccion,
)
from fondos import (
    obtener_info_fondo, obtener_precio_actual, obtener_precio_historico_en_fecha,
    obtener_datos_historicos,
    generar_histograma_personal, generar_reporte_rendimiento,
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
        self.tabview = ctk.CTkTabview(self)
        self.tabview.grid(row=1, column=0, sticky="nsew", padx=10, pady=(5, 0))

        self.tab_agregar = self.tabview.add("Agregar")
        self.tab_inversiones = self.tabview.add("Inversiones")
        self.tab_rendimiento = self.tabview.add("Rendimiento")

        self._build_tab_agregar()
        self._build_tab_inversiones()
        self._build_tab_rendimiento()

    def _build_statusbar(self):
        self.statusbar = ctk.CTkLabel(self, text="Listo", anchor="w", font=("Segoe UI", 11))
        self.statusbar.grid(row=2, column=0, sticky="ew", padx=10, pady=(2, 5))

    def set_status(self, msg):
        if hasattr(self, "statusbar"):
            self.statusbar.configure(text=msg)

    def _build_tab_agregar(self):
        self.tab_agregar.grid_columnconfigure(0, weight=1)
        self.tab_agregar.grid_columnconfigure(1, weight=2)

        row = 0
        ctk.CTkLabel(self.tab_agregar, text="ISIN", anchor="w").grid(row=row, column=0, sticky="w", padx=15, pady=(15, 2))
        f_isin = ctk.CTkFrame(self.tab_agregar, fg_color="transparent")
        f_isin.grid(row=row, column=1, sticky="ew", padx=15, pady=(15, 2))
        f_isin.grid_columnconfigure(0, weight=1)
        self.entry_isin = ctk.CTkEntry(f_isin, placeholder_text="Ej: LU0635178014, IE00B4L5Y983")
        self.entry_isin.grid(row=0, column=0, sticky="ew")
        self.btn_buscar = ctk.CTkButton(f_isin, text="Buscar", width=70, command=self._buscar_fondo)
        self.btn_buscar.grid(row=0, column=1, padx=(5, 0))

        row += 1
        ctk.CTkLabel(self.tab_agregar, text="Ticker FT", anchor="w").grid(row=row, column=0, sticky="w", padx=15, pady=2)
        self.entry_ticker = ctk.CTkEntry(self.tab_agregar, placeholder_text="Ticker en FT (opcional)")
        self.entry_ticker.grid(row=row, column=1, sticky="ew", padx=15, pady=2)

        row += 1
        ctk.CTkLabel(self.tab_agregar, text="Nombre", anchor="w").grid(row=row, column=0, sticky="w", padx=15, pady=2)
        self.entry_nombre = ctk.CTkEntry(self.tab_agregar, placeholder_text="Se autocompleta al buscar")
        self.entry_nombre.grid(row=row, column=1, sticky="ew", padx=15, pady=2)

        row += 1
        ctk.CTkLabel(self.tab_agregar, text="Tipo", anchor="w").grid(row=row, column=0, sticky="w", padx=15, pady=2)
        self.combo_tipo = ctk.CTkComboBox(self.tab_agregar, values=["compra", "venta"], state="readonly")
        self.combo_tipo.set("compra")
        self.combo_tipo.grid(row=row, column=1, sticky="ew", padx=15, pady=2)

        row += 1
        ctk.CTkLabel(self.tab_agregar, text="Participaciones", anchor="w").grid(row=row, column=0, sticky="w", padx=15, pady=2)
        self.entry_participaciones = ctk.CTkEntry(self.tab_agregar, placeholder_text="Número de participaciones")
        self.entry_participaciones.grid(row=row, column=1, sticky="ew", padx=15, pady=2)

        row += 1
        ctk.CTkLabel(self.tab_agregar, text="Precio por participación (NAV)", anchor="w").grid(row=row, column=0, sticky="w", padx=15, pady=2)
        self.entry_precio = ctk.CTkEntry(self.tab_agregar, placeholder_text="NAV unitario")
        self.entry_precio.grid(row=row, column=1, sticky="ew", padx=15, pady=2)

        row += 1
        ctk.CTkLabel(self.tab_agregar, text="Fecha", anchor="w").grid(row=row, column=0, sticky="w", padx=15, pady=2)
        self.entry_fecha = ctk.CTkEntry(self.tab_agregar, placeholder_text="YYYY-MM-DD (dejar vacío = hoy)")
        self.entry_fecha.grid(row=row, column=1, sticky="ew", padx=15, pady=2)

        row += 1
        f_btn = ctk.CTkFrame(self.tab_agregar, fg_color="transparent")
        f_btn.grid(row=row, column=0, columnspan=2, pady=(15, 5))
        self.btn_agregar = ctk.CTkButton(f_btn, text="Agregar Transacción", command=self._agregar_transaccion)
        self.btn_agregar.pack()
        self.lbl_total = ctk.CTkLabel(f_btn, text="", font=("Segoe UI", 13, "bold"))
        self.lbl_total.pack(pady=(5, 0))
        self.lbl_comparacion = ctk.CTkLabel(f_btn, text="", font=("Segoe UI", 12))
        self.lbl_comparacion.pack(pady=(2, 0))

    def _buscar_fondo(self):
        isin = self.entry_isin.get().strip().upper()
        if not isin:
            messagebox.showwarning("Aviso", "Ingresa un ISIN primero.")
            return
        fecha = self.entry_fecha.get().strip() or None
        self.btn_buscar.configure(state="disabled", text="Buscando...")
        self.set_status(f"Buscando información de {isin}...")

        def task():
            info = obtener_info_fondo(isin)
            precio_historico = None
            if fecha and info.get("ticker"):
                precio_historico = obtener_precio_historico_en_fecha(isin, fecha)
            self.after(0, lambda: self._completar_busqueda(isin, info, precio_historico))

        threading.Thread(target=task, daemon=True).start()

    def _completar_busqueda(self, isin, info, precio_historico=None):
        nombre = info.get("nombre") or isin
        self.entry_nombre.delete(0, "end")
        self.entry_nombre.insert(0, nombre)
        ticker = info.get("ticker") or ""
        self.entry_ticker.delete(0, "end")
        self.entry_ticker.insert(0, ticker)
        precio_actual = info.get("precio_actual")
        if precio_historico is not None:
            self.entry_precio.delete(0, "end")
            self.entry_precio.insert(0, str(precio_historico))
            if precio_actual:
                diff = precio_actual - precio_historico
                diff_pct = (diff / precio_historico) * 100
                color = "green" if diff >= 0 else "red"
                tc = self._obtener_tc()
                ph_eur = convertir_a_eur(precio_historico, tipo_cambio=tc)
                pa_eur = convertir_a_eur(precio_actual, tipo_cambio=tc)
                diff_eur = convertir_a_eur(diff, tipo_cambio=tc)
                self.lbl_comparacion.configure(
                    text=f"NAV en fecha: €{ph_eur:.2f}  |  "
                         f"NAV actual: €{pa_eur:.2f}  |  "
                         f"Cambio: [{color}]{diff_eur:+.2f}€ ({diff_pct:+.2f}%)"
                )
        else:
            if precio_actual:
                self.entry_precio.delete(0, "end")
                self.entry_precio.insert(0, str(precio_actual))
            self.lbl_comparacion.configure(text="")
        self.btn_buscar.configure(state="normal", text="Buscar")
        self.set_status(f"Información de {isin} cargada.")

    def _agregar_transaccion(self):
        isin = self.entry_isin.get().strip().upper()
        nombre = self.entry_nombre.get().strip()
        ticker = self.entry_ticker.get().strip().upper()
        tipo = self.combo_tipo.get()
        fecha = self.entry_fecha.get().strip() or None

        if not isin:
            messagebox.showwarning("Aviso", "El ISIN es obligatorio.")
            return
        if not nombre:
            messagebox.showwarning("Aviso", "El nombre es obligatorio.")
            return

        try:
            participaciones = float(self.entry_participaciones.get().strip())
            if participaciones <= 0:
                raise ValueError
        except (ValueError, AttributeError):
            messagebox.showwarning("Aviso", "Ingresa un número válido de participaciones.")
            return

        try:
            precio = float(self.entry_precio.get().strip())
            if precio <= 0:
                raise ValueError
        except (ValueError, AttributeError):
            messagebox.showwarning("Aviso", "Ingresa un precio válido.")
            return

        try:
            if fecha:
                datetime.strptime(fecha, "%Y-%m-%d")
        except ValueError:
            messagebox.showwarning("Aviso", "Fecha inválida. Usa el formato YYYY-MM-DD.")
            return

        total = round(participaciones * precio, 2)
        trans_id = agregar_transaccion(isin, nombre, tipo, participaciones, precio, total, fecha, ticker=ticker)

        tc = self._obtener_tc()
        total_eur = convertir_a_eur(total, tipo_cambio=tc)
        self.set_status(f"Transacción #{trans_id} registrada: {tipo} de {participaciones} {isin}")
        if total_eur is not None:
            messagebox.showinfo("OK", f"Transacción registrada (ID: {trans_id})\nTotal: €{total_eur:,.2f}")
        else:
            messagebox.showinfo("OK", f"Transacción registrada (ID: {trans_id})\nTotal: ${total:,.2f}")

        self.entry_isin.delete(0, "end")
        self.entry_ticker.delete(0, "end")
        self.entry_nombre.delete(0, "end")
        self.entry_participaciones.delete(0, "end")
        self.entry_precio.delete(0, "end")
        self.entry_fecha.delete(0, "end")
        self.lbl_total.configure(text="")
        self.tabview.set("Inversiones")
        self._cargar_inversiones_inicial()
        self._refrescar_inversiones_background()

    def _build_tab_inversiones(self):
        self.tab_inversiones.grid_rowconfigure(0, weight=1)
        self.tab_inversiones.grid_columnconfigure(0, weight=1)

        frame = ctk.CTkFrame(self.tab_inversiones)
        frame.grid(row=0, column=0, sticky="nsew", padx=10, pady=10)
        frame.grid_rowconfigure(0, weight=1)
        frame.grid_columnconfigure(0, weight=1)

        style = ttk.Style()
        style.theme_use("clam")
        style.configure("Treeview", rowheight=26, font=("Segoe UI", 11))
        style.configure("Treeview.Heading", font=("Segoe UI", 11, "bold"))
        style.map("Treeview", background=[("selected", "#2e7d32")])

        cols = ("id", "fecha", "isin", "nombre", "tipo", "part", "nav_compra", "nav_actual", "cambio", "total")
        self.tree_inversiones = ttk.Treeview(frame, columns=cols, show="headings", height=15)
        headings = [
            ("id", "ID", 40),
            ("fecha", "Fecha", 100),
            ("isin", "ISIN", 130),
            ("nombre", "Nombre", 180),
            ("tipo", "Tipo", 70),
            ("part", "Part.", 80),
            ("nav_compra", "NAV en fecha", 110),
            ("nav_actual", "NAV actual", 100),
            ("cambio", "Cambio", 110),
            ("total", "Total", 100),
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
        self.lbl_resumen_inv.grid(row=2, column=0, sticky="ew", padx=15, pady=(0, 8))

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
                f"{part:.4f}", formatear(precio_eur), "---", "---", formatear(total_eur),
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

    def _build_tab_rendimiento(self):
        self.tab_rendimiento.grid_rowconfigure(1, weight=1)
        self.tab_rendimiento.grid_rowconfigure(2, weight=0)
        self.tab_rendimiento.grid_columnconfigure(0, weight=1)

        frame_controls = ctk.CTkFrame(self.tab_rendimiento, fg_color="transparent")
        frame_controls.grid(row=0, column=0, sticky="ew", pady=(5, 2))
        frame_controls.grid_columnconfigure(1, weight=1)

        ctk.CTkLabel(frame_controls, text="ISIN:", font=("Segoe UI", 13)).grid(row=0, column=0, padx=(10, 5), pady=5)
        self.entry_rend_isin = ctk.CTkEntry(frame_controls, placeholder_text="ISIN del fondo")
        self.entry_rend_isin.grid(row=0, column=1, sticky="ew", padx=5, pady=5)

        self.btn_rendimiento = ctk.CTkButton(frame_controls, text="Ver Rendimiento", command=self._ver_rendimiento)
        self.btn_rendimiento.grid(row=0, column=2, padx=5, pady=5)
        self.btn_histograma = ctk.CTkButton(frame_controls, text="Generar Gráfico P&L", command=self._generar_histograma)
        self.btn_histograma.grid(row=0, column=3, padx=5, pady=5)
        self.btn_abrir_grafico = ctk.CTkButton(frame_controls, text="Abrir", width=60, command=self._abrir_grafico)
        self.btn_abrir_grafico.grid(row=0, column=4, padx=5, pady=5)

        paned = ctk.CTkFrame(self.tab_rendimiento)
        paned.grid(row=1, column=0, sticky="nsew", padx=10, pady=5)
        paned.grid_rowconfigure(0, weight=1)
        paned.grid_columnconfigure(0, weight=1)
        paned.grid_columnconfigure(1, weight=2)

        self.txt_rendimiento = ctk.CTkTextbox(paned, font=("Consolas", 12), wrap="word")
        self.txt_rendimiento.grid(row=0, column=0, sticky="nsew", padx=(0, 5))

        self.lbl_histograma_img = ctk.CTkLabel(paned, text="Genera un gráfico para verlo aquí", anchor="center",
                                                font=("Segoe UI", 13))
        self.lbl_histograma_img.grid(row=0, column=1, sticky="nsew")

        self.lbl_histograma_ruta = ctk.CTkLabel(self.tab_rendimiento, text="", font=("Segoe UI", 11))
        self.lbl_histograma_ruta.grid(row=2, column=0, sticky="ew", padx=10, pady=(0, 5))

    def _ver_rendimiento(self):
        isin = self.entry_rend_isin.get().strip().upper()
        if not isin:
            messagebox.showwarning("Aviso", "Ingresa un ISIN primero.")
            return
        self.btn_rendimiento.configure(state="disabled", text="Cargando...")
        self.set_status(f"Obteniendo datos históricos de {isin}...")

        def task():
            df = obtener_datos_historicos(isin)
            reporte = generar_reporte_rendimiento(df) if df is not None and not df.empty else "No se pudieron obtener datos históricos."
            self.after(0, lambda: self._mostrar_reporte(reporte))

        threading.Thread(target=task, daemon=True).start()

    def _mostrar_reporte(self, reporte):
        self.txt_rendimiento.delete("0.0", "end")
        self.txt_rendimiento.insert("0.0", reporte)
        self.btn_rendimiento.configure(state="normal", text="Ver Rendimiento")
        self.set_status("Reporte de rendimiento listo.")

    def _generar_histograma(self):
        isin = self.entry_rend_isin.get().strip().upper()
        if not isin:
            messagebox.showwarning("Aviso", "Ingresa un ISIN primero.")
            return
        self.btn_histograma.configure(state="disabled", text="Generando...")
        self.set_status(f"Generando histograma de rendimiento personal para {isin}...")

        def task():
            df = obtener_datos_historicos(isin)
            if df is None or df.empty:
                self.after(0, lambda: self._mostrar_histograma_resultado(None, isin))
                return
            resumen = obtener_resumen_isin(isin)
            if not resumen:
                self.after(0, lambda: self._mostrar_histograma_resultado(None, isin,
                    msg="No hay transacciones para este ISIN en tu portafolio."))
                return
            pos = resumen[0]
            participaciones = pos["total_participaciones"]
            total_invertido = pos["total_invertido"]
            info = obtener_info_fondo(isin)
            nombre = info.get("nombre", isin)
            archivo = generar_histograma_personal(df, participaciones, total_invertido, isin, nombre)
            self.after(0, lambda: self._mostrar_histograma_resultado(archivo, isin))

        threading.Thread(target=task, daemon=True).start()

    def _mostrar_histograma_resultado(self, archivo, isin, msg=""):
        self._ultimo_grafico = archivo
        if archivo and os.path.exists(archivo):
            try:
                pil_img = Image.open(archivo)
                ctk_img = ctk.CTkImage(light_image=pil_img, dark_image=pil_img, size=(700, 350))
                self.lbl_histograma_img.configure(image=ctk_img, text="")
                self.lbl_histograma_img.image = ctk_img
                self.lbl_histograma_ruta.configure(
                    text=f"Gráfico guardado en: {archivo}",
                    text_color="lightblue"
                )
                self.set_status(f"Gráfico P&L generado para {isin}.")
            except Exception as e:
                self.lbl_histograma_img.configure(text=f"Error al mostrar imagen: {e}", image="")
                self.lbl_histograma_ruta.configure(text="")
        else:
            self.lbl_histograma_img.configure(text=msg or "No se pudo generar el gráfico (datos insuficientes).")
            self.lbl_histograma_ruta.configure(text="")
        self.btn_histograma.configure(state="normal", text="Generar Gráfico P&L")
        self.set_status("Proceso completado.")

    def _abrir_grafico(self):
        if hasattr(self, "_ultimo_grafico") and self._ultimo_grafico and os.path.exists(self._ultimo_grafico):
            os.startfile(self._ultimo_grafico)
        else:
            messagebox.showinfo("Aviso", "Genera un gráfico primero.")


if __name__ == "__main__":
    app = App()
    app.mainloop()
