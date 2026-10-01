"""Bibliotheque par defaut de modules electroniques (cotes approximatives, a verifier au pied a coulisse)."""

DEFAULT_COMPONENTS = [
    {
        "id": "ssd1306_096",
        "name": "OLED SSD1306 0.96\" 128x64",
        "category": "Ecran",
        "description": "Module OLED 0.96 pouce I2C/SPI (4 ou 7 broches), controleur SSD1306. Zone visible decalee vers le haut (nappe en bas du verre).",
        "dims": {
            "pcb_w": 27.3, "pcb_h": 27.8, "pcb_t": 1.2,
            "glass_w": 26.7, "glass_h": 19.3, "glass_t": 1.5,
            "glass_offset_x": 0.0, "glass_offset_y": -0.6,
            "view_w": 23.0, "view_h": 12.0,
            "view_offset_x": 0.0, "view_offset_y": 1.6,
            "hole_d": 2.0, "hole_dx": 23.0, "hole_dy": 23.5,
        },
        "builtin": True,
    },
    {
        "id": "sh1106_13",
        "name": "OLED SH1106 1.3\" 128x64",
        "category": "Ecran",
        "description": "Module OLED 1.3 pouce I2C/SPI, controleur SH1106. Zone visible decalee vers le haut.",
        "dims": {
            "pcb_w": 35.4, "pcb_h": 33.5, "pcb_t": 1.2,
            "glass_w": 34.5, "glass_h": 23.0, "glass_t": 1.6,
            "glass_offset_x": 0.0, "glass_offset_y": -1.0,
            "view_w": 30.0, "view_h": 15.2,
            "view_offset_x": 0.0, "view_offset_y": 2.0,
            "hole_d": 3.0, "hole_dx": 30.4, "hole_dy": 28.3,
        },
        "builtin": True,
    },
]

DIM_LABELS = {
    "pcb_w": "Largeur PCB", "pcb_h": "Hauteur PCB", "pcb_t": "Épaisseur PCB",
    "glass_w": "Largeur verre", "glass_h": "Hauteur verre", "glass_t": "Épaisseur verre",
    "glass_offset_x": "Décalage X verre/PCB", "glass_offset_y": "Décalage Y verre/PCB",
    "view_w": "Largeur zone visible", "view_h": "Hauteur zone visible",
    "view_offset_x": "Décalage X zone visible/verre", "view_offset_y": "Décalage Y zone visible/verre",
    "hole_d": "Diamètre trous", "hole_dx": "Entraxe trous X", "hole_dy": "Entraxe trous Y",
}
