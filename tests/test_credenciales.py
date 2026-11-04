from PIL import Image

from dep_leon import credenciales


def test_genera_pdf_con_y_sin_foto_y_varias_hojas(conn, infantil_id, torneo_id, tmp_path):
    categoria = conn.execute(
        "SELECT id FROM categorias WHERE liga_id = ? AND nombre = '2015-2016'", (infantil_id,)
    ).fetchone()["id"]
    Image.new("RGB", (200, 300), "blue").save(tmp_path / "f.jpg")
    with conn:
        equipo = conn.execute(
            "INSERT INTO equipos (torneo_id, categoria_id, nombre) VALUES (?, ?, 'Pegasos')",
            (torneo_id, categoria),
        ).lastrowid
        for numero in range(9):  # caben 8 por hoja
            conn.execute(
                "INSERT INTO jugadores (equipo_id, nombre, fecha_nacimiento, numero, foto) "
                "VALUES (?, ?, '2015-03-15', ?, ?)",
                (equipo, f"Jugador con nombre muy largo número {numero}", numero, "f.jpg" if numero else ""),
            )

    destino = tmp_path / "c.pdf"
    assert credenciales.generar(conn, equipo, destino, tmp_path) == 9
    contenido = destino.read_bytes()
    assert contenido.startswith(b"%PDF")
    assert contenido.count(b"/Type /Page\n") + contenido.count(b"/Type /Page ") >= 2
