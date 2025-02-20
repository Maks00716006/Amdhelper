import cv2
import numpy as np
import qrcode
import json
import os
from PIL import Image


def generate_template( question_count=20, option_count=4, columns=2, margin=50, question_spacing=60,
                      column_spacing=100):
    """Генерирует изображение шаблона теста с QR-кодом."""
    image_path = f'template_{question_count}_{option_count}_{columns}.jpg'  # Изменено имя файла
    # Параметры черного периметра
    border_thickness = 5  # Толщина черного периметра
    border_margin = 10  # Отступ от края изображения до периметра
    side_qr = 200

    option_spacing = 20
    start_x = margin + border_thickness  # Учитываем отступ от периметра
    start_y = margin + border_thickness  # Учитываем отступ от периметра
    option_width = 30
    option_height = 30

    rows = int(np.ceil(question_count / columns))
    height = margin*2 + border_thickness*2 + border_margin*2 + (rows-1) * question_spacing + side_qr
    # Ширина зависит от количества столбцов и фиксированного расстояния между ними
    width = margin * 2 + (columns - 1) * column_spacing + columns * (
                option_count * (30 + 20))  # 30 — ширина варианта ответа, 20 — отступ между вариантами

    # Рассчитываем размер изображения
    width, height = int(width), int(height)

    # Уменьшаем размер изображения до размера периметра
    image_width = width - 2 * border_margin
    image_height = height - 2 * border_margin

    # QR-код
    qr_data = {
        "question_count": question_count,
        "option_count": option_count,
        "columns": columns,
        "margin": margin,
        "question_spacing": question_spacing,
        "column_spacing": column_spacing,
        "border_thickness": border_thickness,  # Добавляем толщину периметра
        "border_margin": border_margin,  # Добавляем отступ от края
        "image_width": image_width,  # Добавляем ширину изображения
        "image_height": image_height  # Добавляем высоту изображения
    }

    qr_text = json.dumps(qr_data, ensure_ascii=False)

    qr = qrcode.QRCode(version=1, error_correction=qrcode.constants.ERROR_CORRECT_L, box_size=8, border=2)
    qr.add_data(qr_text)
    qr.make(fit=True)

    qr_img = qr.make_image(fill_color="black", back_color="white")
    qr_img_pil = qr_img.convert("RGB")  # convert to RGB
    qr_img_np = np.array(qr_img_pil)  # now convert to numpy array

    # Фиксированный размер QR-кода: 200x200 пикселей
    qr_img_np_scaled = cv2.resize(qr_img_np, (side_qr, side_qr), interpolation=cv2.INTER_AREA)


    # Вычисляем y-координату самой низкой строки с вопросами

    last_question_y = margin + border_thickness + (rows - 1) * question_spacing + option_height

    # Определяем минимальную высоту, чтобы поместить QR-код
    min_qr_y = last_question_y + 20

    # Если QR-код не помещается, увеличиваем высоту изображения
    if min_qr_y + side_qr > image_height:
        image_height = min_qr_y + side_qr

    # Создаем изображение
    image = np.ones((image_height, image_width, 3), dtype=np.uint8) * 255  # Белый фон

    # Параметры расположения


    font = cv2.FONT_HERSHEY_SIMPLEX
    font_scale = 0.5
    font_color = (0, 0, 0)
    font_thickness = 1

    # Переделанная логика для вопросов сверху вниз
    for i in range(question_count):
        col_index = i // rows  # Номер столбца
        row_index = i % rows  # Номер строки в столбце

        # Пишем номер вопроса (левее первого квадрата)
        question_number_x = start_x + col_index * (column_spacing + option_count * (
                    option_width + option_spacing)) - 40  # Смещаем влево на 40 пикселей
        question_number_y = start_y + row_index * question_spacing + 15

        cv2.putText(image, str(i + 1), (question_number_x, question_number_y), font, font_scale, font_color,
                    font_thickness)

        for j in range(option_count):
            x = start_x + j * (option_width + option_spacing) + col_index * (
                        column_spacing + option_count * (option_width + option_spacing))
            y = start_y + row_index * question_spacing

            # Рисуем квадраты вариантов ответа
            cv2.rectangle(image, (x, y), (x + option_width, y + option_height), (0, 0, 0), 1)  # Черный контур

            # Пишем название варианта ответа
            option_label = chr(ord('A') + j)  # A, B, C, D, ...
            label_x = x
            label_y = y - 5
            cv2.putText(image, option_label, (label_x, label_y), font, font_scale, font_color, font_thickness)

    # Расположение QR-кода (в нижнем правом углу)

    # Вычисляем x координату
    qr_x = image_width - side_qr - margin - border_thickness  # Учитываем отступ от периметра
    qr_y = image_height - side_qr - border_thickness  # Учитываем отступ от периметра

    # Вставляем QR-код в основное изображение
    image[qr_y:qr_y + side_qr, qr_x:qr_x + side_qr] = qr_img_np_scaled

    # Нижняя граница изображения совпадает с нижней границей периметра
    bottom_border_y = qr_y + side_qr + border_thickness

    # Рисуем периметр
    cv2.rectangle(image, (0, 0), (image_width, bottom_border_y), (0, 0, 0), border_thickness)

    # Создаем PIL image из numpy array
    image_pil = Image.fromarray(image)

    # Сохраняем изображение с тестом
    # test_image_path = os.path.splitext(image_path)[0] + ".jpg"  # Save jpg image
    # image_pil.save(test_image_path)

    # print(f"Сгенерировано изображение теста: {test_image_path}")

    return image  # Возвращаем изображение


if __name__ == "__main__":
    question_count = 10  # Задайте желаемое количество вопросов
    option_count = 4  # Задайте желаемое количество вариантов ответа
    columns = 2  # Задайте желаемое количество столбцов с вопросами
    margin = 50  # Задайте желаемый отступ от краев
    question_spacing = 60  # Задайте желаемое расстояние между вопросами
    column_spacing = 100  # Фиксированное расстояние между столбцами: 200 пикселей


    image = generate_template(

        question_count=question_count,
        option_count=option_count,
        columns=columns,
        margin=margin,
        question_spacing=question_spacing,
        column_spacing=column_spacing
    )
