import os
import sqlite3
from pathlib import Path
from fastapi import FastAPI, File, UploadFile, HTTPException
from fastapi.responses import FileResponse
from PyQt5.QtWidgets import (
    QApplication, QLabel, QVBoxLayout, QWidget, QPushButton, QTableWidget,
    QTableWidgetItem, QHeaderView, QFileDialog, QMessageBox, QHBoxLayout, QFrame,
    QCheckBox, QLineEdit
)
from PyQt5.QtCore import Qt, QTimer
from PyQt5.QtGui import QIcon
import threading
import shutil
import time

# Configuración inicial
app = FastAPI()
UPLOAD_FOLDER = "uploads"
BACKUP_FOLDER = "backups"
Path(UPLOAD_FOLDER).mkdir(exist_ok=True)  # Crear la carpeta si no existe
Path(BACKUP_FOLDER).mkdir(exist_ok=True)  # Crear carpeta para backups
DATABASE = "files.db"

# Inicializar la base de datos
def init_db():
    with sqlite3.connect(DATABASE) as conn:
        cursor = conn.cursor()
        cursor.execute("""
            CREATE TABLE IF NOT EXISTS files (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                filename TEXT NOT NULL,
                filepath TEXT NOT NULL,
                upload_date TEXT NOT NULL
            )
        """)
        conn.commit()

init_db()

# Función auxiliar para consultas SQL
def db_query(query: str, params=(), fetchone=False):
    with sqlite3.connect(DATABASE) as conn:
        cursor = conn.cursor()
        cursor.execute(query, params)
        conn.commit()
        return cursor.fetchone() if fetchone else cursor.fetchall()

# Decorador para manejar excepciones
def handle_errors(func):
    async def wrapper(*args, **kwargs):
        try:
            return await func(*args, **kwargs)
        except Exception as e:
            raise HTTPException(status_code=500, detail=str(e))
    return wrapper

# Endpoints de la API
@app.post("/upload/")
@handle_errors
async def upload_file(file: UploadFile = File(...)):
    timestamp = int(time.time())  # Obtenemos la marca de tiempo actual
    file_path = os.path.join(UPLOAD_FOLDER, file.filename)
    upload_date = time.strftime('%Y-%m-%d %H:%M:%S', time.localtime(timestamp))  # Formato de fecha legible
    with open(file_path, "wb") as f:
        f.write(await file.read())
    db_query("INSERT INTO files (filename, filepath, upload_date) VALUES (?, ?, ?)",
             (file.filename, file_path, upload_date))
    return {"message": f"Archivo '{file.filename}' subido exitosamente."}

@app.get("/download/{filename}")
@handle_errors
async def download_file(filename: str):
    result = db_query("SELECT filepath FROM files WHERE filename = ?", (filename,), fetchone=True)
    if not result:
        raise HTTPException(status_code=404, detail=f"Archivo '{filename}' no encontrado.")
    return FileResponse(result[0], filename=filename)

@app.delete("/delete/{filename}")
@handle_errors
async def delete_file(filename: str):
    result = db_query("SELECT filepath FROM files WHERE filename = ?", (filename,), fetchone=True)
    if not result:
        raise HTTPException(status_code=404, detail=f"Archivo '{filename}' no encontrado.")
    filepath = result[0]
    os.remove(filepath)  # Eliminar archivo
    db_query("DELETE FROM files WHERE filename = ?", (filename,))
    return {"message": f"Archivo '{filename}' eliminado exitosamente."}

@app.get("/files/")
@handle_errors
async def list_files():
    return {"files": [row[0] for row in db_query("SELECT filename FROM files")]}

@app.post("/backup/")
@handle_errors
async def create_backup():
    """
    Crea un backup de la base de datos y lo guarda en la carpeta 'backups'.
    """
    timestamp = int(time.time())  # Obtenemos la marca de tiempo actual
    backup_path = os.path.join(BACKUP_FOLDER, f"backup_{timestamp}.db")
    try:
        shutil.copyfile(DATABASE, backup_path)
        return {"message": f"Backup creado exitosamente: {backup_path}"}
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"No se pudo crear el backup: {str(e)}")

# Interfaz gráfica con PyQt5
class GestorArchivos(QWidget):
    def __init__(self):
        super().__init__()
        self.init_ui()
        self.auto_backup_timer = None  # Temporizador para el respaldo automático

    def init_ui(self):
        self.setWindowTitle("NAS SERVICE")
        self.setGeometry(100, 100, 800, 600)
        self.setStyleSheet("""
            QWidget { background-color: #000; color: #FFF; font-family: Arial; }
            QLabel { font-size: 20px; }
            QPushButton { background-color: #4CAF50; color: white; border: none; padding: 10px; border-radius: 5px; }
            QPushButton:hover { background-color: #45A049; }
            QLineEdit { background-color: #1C1C1C; color: white; border: 1px solid #333; padding: 5px; border-radius: 5px; }
            QTableWidget { background-color: #1C1C1C; color: white; border: 1px solid #333; gridline-color: #444; }
            QHeaderView::section { background-color: #2C2C2C; color: white; padding: 5px; }
        """)
        layout = QVBoxLayout()

        # Título principal
        etiqueta_titulo = QLabel("NAS SERVICE")
        etiqueta_titulo.setAlignment(Qt.AlignCenter)
        layout.addWidget(etiqueta_titulo)

        # Área de arrastrar y soltar
        self.drop_area = QLabel("Arrastra y suelta archivos aquí", self)
        self.drop_area.setAlignment(Qt.AlignCenter)
        self.drop_area.setStyleSheet("""
            QLabel {
                background-color: #2C2C2C;
                border: 2px dashed #4CAF50;
                color: #CCC;
                font-size: 16px;
                padding: 20px;
                border-radius: 10px;
            }
        """)
        self.drop_area.setAcceptDrops(True)
        layout.addWidget(self.drop_area)

        # Botón para subir archivos
        boton_subir = QPushButton("Subir Archivo", self)
        boton_subir.setIcon(QIcon("upload_icon.png"))
        boton_subir.clicked.connect(self.subir_archivo)
        layout.addWidget(boton_subir)

        # Tabla para mostrar archivos
        self.tabla = QTableWidget()
        self.tabla.setColumnCount(3)  # Nombre, Fecha, Acciones
        self.tabla.setHorizontalHeaderLabels(["Nombre", "Fecha de Subida", "Acciones"])
        self.tabla.horizontalHeader().setSectionResizeMode(QHeaderView.Stretch)
        layout.addWidget(self.tabla)

        # Separador visual
        separador = QFrame()
        separador.setFrameShape(QFrame.HLine)
        separador.setFrameShadow(QFrame.Sunken)
        layout.addWidget(separador)

        # Botón para crear backup
        boton_backup = QPushButton("Crear Backup")
        boton_backup.setIcon(QIcon("backup_icon.png"))
        boton_backup.clicked.connect(self.crear_backup)
        layout.addWidget(boton_backup)

        # Switch y campo para configurar tiempo de guardado automático
        self.switch_guardado_automatico = QCheckBox("Guardado automático activado")
        self.input_tiempo_guardado = QLineEdit()
        self.input_tiempo_guardado.setPlaceholderText("Tiempo en segundos...")
        self.input_tiempo_guardado.setText("60")  # Valor por defecto: 60 segundos
        self.input_tiempo_guardado.setEnabled(False)  # Desactivado por defecto
        self.switch_guardado_automatico.stateChanged.connect(self.toggle_guardado_automatico)
        layout.addWidget(self.switch_guardado_automatico)
        layout.addWidget(self.input_tiempo_guardado)

        # Etiqueta para mostrar el estado del disco
        self.etiqueta_estado_disco = QLabel("Estado del disco: Funcionando")
        self.etiqueta_estado_disco.setAlignment(Qt.AlignCenter)
        self.etiqueta_estado_disco.setStyleSheet("font-size: 14px; color: #4CAF50;")
        layout.addWidget(self.etiqueta_estado_disco)

        # Verificar estado del disco al iniciar
        self.verificar_estado_disco()

        # Etiqueta de pie de página
        etiqueta_pie = QLabel("© 2025 - NAS SERVICE")
        etiqueta_pie.setAlignment(Qt.AlignCenter)
        etiqueta_pie.setStyleSheet("font-size: 12px; color: #CCC;")
        layout.addWidget(etiqueta_pie)

        # Asignar el layout a la ventana
        self.setLayout(layout)

        # Temporizador para actualizar la tabla automáticamente
        self.timer = QTimer()
        self.timer.timeout.connect(self.cargar_archivos)
        self.timer.start(5000)
        self.cargar_archivos()

    def cargar_archivos(self):
        self.tabla.setRowCount(0)
        for nombre, ruta, fecha in db_query("SELECT filename, filepath, upload_date FROM files"):
            fila = self.tabla.rowCount()
            self.tabla.insertRow(fila)
            self.tabla.setItem(fila, 0, QTableWidgetItem(nombre))
            self.tabla.setItem(fila, 1, QTableWidgetItem(fecha))
            self.tabla.setCellWidget(fila, 2, self.crear_botones_acciones(ruta))

    def crear_botones_acciones(self, ruta):
        layout_botones = QHBoxLayout()
        layout_botones.setContentsMargins(0, 0, 0, 0)
        boton_descargar = QPushButton("Descargar")
        boton_descargar.setIcon(QIcon("download_icon.png"))
        boton_descargar.clicked.connect(lambda _, r=ruta: self.descargar_archivo(r))
        layout_botones.addWidget(boton_descargar)
        boton_eliminar = QPushButton("Eliminar")
        boton_eliminar.setIcon(QIcon("delete_icon.png"))
        boton_eliminar.clicked.connect(lambda _, r=ruta: self.eliminar_archivo(r))
        layout_botones.addWidget(boton_eliminar)
        contenedor = QWidget()
        contenedor.setLayout(layout_botones)
        return contenedor

    def subir_archivo(self):
        archivos = QFileDialog.getOpenFileNames(self, "Seleccionar Archivos", "", "Todos los archivos (*);;")[0]
        if archivos:
            self.procesar_archivos(archivos)

    def procesar_archivos(self, archivos):
        for archivo in archivos:
            try:
                nombre_base, extension = os.path.splitext(os.path.basename(archivo))
                timestamp = int(time.time())
                nuevo_nombre = f"{nombre_base}_{timestamp}{extension}"
                destino = os.path.join(UPLOAD_FOLDER, nuevo_nombre)
                upload_date = time.strftime('%Y-%m-%d %H:%M:%S', time.localtime(timestamp))
                shutil.copyfile(archivo, destino)
                db_query("INSERT INTO files (filename, filepath, upload_date) VALUES (?, ?, ?)",
                         (nuevo_nombre, destino, upload_date))
            except Exception as e:
                QMessageBox.critical(self, "Error", f"No se pudo subir el archivo '{os.path.basename(archivo)}': {str(e)}")
        self.cargar_archivos()
        QMessageBox.information(self, "Éxito", "Archivos subidos exitosamente.")

    def descargar_archivo(self, ruta):
        destino = QFileDialog.getSaveFileName(self, "Guardar Archivo", os.path.basename(ruta), "Todos los archivos (*);;")[0]
        if destino:
            try:
                shutil.copyfile(ruta, destino)
                QMessageBox.information(self, "Éxito", "Archivo descargado correctamente.")
            except Exception as e:
                QMessageBox.critical(self, "Error", f"No se pudo descargar el archivo: {str(e)}")

    def eliminar_archivo(self, ruta):
        try:
            os.remove(ruta)
            db_query("DELETE FROM files WHERE filepath = ?", (ruta,))
            self.cargar_archivos()
            QMessageBox.information(self, "Éxito", "Archivo eliminado correctamente.")
        except Exception as e:
            QMessageBox.critical(self, "Error", f"No se pudo eliminar el archivo: {str(e)}")

    def crear_backup(self):
        timestamp = int(time.time())
        backup_path = os.path.join(BACKUP_FOLDER, f"backup_{timestamp}.db")
        try:
            shutil.copyfile(DATABASE, backup_path)
            QMessageBox.information(self, "Éxito", f"Backup creado exitosamente: {backup_path}")
        except Exception as e:
            QMessageBox.critical(self, "Error", f"No se pudo crear el backup: {str(e)}")

    def toggle_guardado_automatico(self, state):
        """
        Activa o desactiva el guardado automático de archivos.
        """
        self.input_tiempo_guardado.setEnabled(state == Qt.Checked)

        if state == Qt.Checked:
            try:
                tiempo = int(self.input_tiempo_guardado.text())
                if tiempo <= 0:
                    raise ValueError("El tiempo debe ser mayor a 0.")
                # Iniciar el guardado automático
                self.iniciar_guardado_automatico(tiempo)
            except ValueError as e:
                QMessageBox.warning(self, "Advertencia", f"Entrada inválida: {str(e)}")
                self.switch_guardado_automatico.setChecked(False)
        else:
            # Detener el guardado automático si está activo
            if self.auto_backup_timer:
                self.auto_backup_timer.stop()
                self.auto_backup_timer = None

    def iniciar_guardado_automatico(self, tiempo):
        """
        Inicia el temporizador para el guardado automático.
        """
        if self.auto_backup_timer:
            self.auto_backup_timer.stop()

        self.auto_backup_timer = QTimer()
        self.auto_backup_timer.timeout.connect(self.crear_backup)
        self.auto_backup_timer.start(tiempo * 1000)  # Convertir segundos a milisegundos

    def verificar_estado_disco(self):
        """
        Verifica si el disco está funcionando correctamente.
        Intenta escribir y leer un archivo temporal en el directorio de subida.
        """
        try:
            test_file = os.path.join(UPLOAD_FOLDER, "test_file.tmp")
            with open(test_file, "w") as f:
                f.write("Test")
            with open(test_file, "r") as f:
                content = f.read()
            os.remove(test_file)
            if content == "Test":
                self.etiqueta_estado_disco.setText("Estado del disco: Funcionando")
                self.etiqueta_estado_disco.setStyleSheet("font-size: 14px; color: #4CAF50;")
            else:
                raise Exception("El contenido del archivo no coincide.")
        except Exception as e:
            self.etiqueta_estado_disco.setText(f"Estado del disco: Fallando ({str(e)})")
            self.etiqueta_estado_disco.setStyleSheet("font-size: 14px; color: #FF5733;")

    def dragEnterEvent(self, event):
        if event.mimeData().hasUrls():
            event.acceptProposedAction()

    def dropEvent(self, event):
        if event.mimeData().hasUrls():
            archivos = [url.toLocalFile() for url in event.mimeData().urls() if os.path.isfile(url.toLocalFile())]
            self.procesar_archivos(archivos)
            event.acceptProposedAction()

# Iniciar la API en un hilo separado
def iniciar_api():
    import uvicorn
    uvicorn.run(app, host="127.0.0.1", port=8000)

# Iniciar la aplicación
if __name__ == "__main__":
    threading.Thread(target=iniciar_api, daemon=True).start()
    app_gui = QApplication([])
    ventana = GestorArchivos()
    ventana.show()
    app_gui.exec_()
