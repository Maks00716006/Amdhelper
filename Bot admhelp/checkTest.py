import cv2
import numpy as np
import json
from pyzbar.pyzbar import decode


def contour_alignment(image_gray, true_height, true_width):
    """ Выравнивание контура"""

    # Применяем бинаризацию (только черный и белый)
    _, image = cv2.threshold(image_gray, 127, 255, cv2.THRESH_BINARY)

    # Находим контуры
    contours, _ = cv2.findContours(image, cv2.RETR_TREE, cv2.CHAIN_APPROX_SIMPLE)

    # Ищем самый большой контур с 4 вершинами
    largest_contour = None
    max_area = 0

    for contour in contours:

        # Аппроксимируем контур
        epsilon = 0.01 * cv2.arcLength(contour, True)
        approx = cv2.approxPolyDP(contour, epsilon, True)

        # Если контур имеет 4 вершины, это может быть квадрат
        if len(approx) == 4:
            # Вычисляем площадь контура
            area = cv2.contourArea(approx)

            # Если площадь больше текущей максимальной, обновляем
            if area > max_area:
                max_area = area
                largest_contour = approx

    # Если найден квадрат
    if largest_contour is not None:

        # Упорядочиваем точки контура (top-left, top-right, bottom-right, bottom-left)
        points = largest_contour.reshape(4, 2)
        rect = np.zeros((4, 2), dtype="float32")

        # Сумма координат будет минимальной у top-left и максимальной у bottom-right
        s = points.sum(axis=1)
        rect[0] = points[np.argmin(s)]  # top-left
        rect[2] = points[np.argmax(s)]  # bottom-right

        # Разница координат будет минимальной у top-right и максимальной у bottom-left
        diff = np.diff(points, axis=1)
        rect[1] = points[np.argmin(diff)]  # top-right
        rect[3] = points[np.argmax(diff)]  # bottom-left

        # Задаем размеры выходного изображения (например, 800x800)
        width, height = true_width, true_height
        dst = np.array([
            [0, 0],
            [width, 0],
            [width, height],
            [0, height]
        ], dtype="float32")

        # Вычисляем матрицу перспективного преобразования
        M = cv2.getPerspectiveTransform(rect, dst)

        # Применяем преобразование
        alig_image = cv2.warpPerspective(image, M, (width, height))

        return alig_image

    else:
        print("Квадрат не найден.")
        return None


def find_qr_code(image_gray):
    """
    Находит второй по величине контур на изображении.

    По нашим предположениям второй по величине контур на изображении
    должен оказаться QR-code
    """

    # Производим размытие изображения для исключения шумов
    blurred = cv2.GaussianBlur(image_gray, (5, 5), 0)

    # Производим адаптивную бинаризацию изображения и инвертируем его
    thresh = cv2.adaptiveThreshold(blurred, 255, cv2.ADAPTIVE_THRESH_GAUSSIAN_C, cv2.THRESH_BINARY, 11, 2)
    thresh = cv2.bitwise_not(thresh)

    # Находим контуры на изображении
    contours, _ = cv2.findContours(thresh, cv2.RETR_LIST, cv2.CHAIN_APPROX_SIMPLE)

    if contours:
        contours = sorted(contours, key=cv2.contourArea, reverse=True)
        if len(contours) > 1:
            second_largest_contour = contours[1]  # Второй по величине контур
            return second_largest_contour
        else:
            print("Ошибка: Не найдено второго контура на изображении.")
            return None
    else:
        print("Ошибка: Не найдено контуров на изображении.")
        return None


def decode_qr_codes(contour_image):
    """Декодирует все QR-коды из изображения контура с помощью pyzbar."""
    decoded_data_list = []
    try:
        decoded_objects = decode(contour_image)
        for obj in decoded_objects:
            try:
                qr_data = json.loads(obj.data.decode('utf-8'))
                decoded_data_list.append((qr_data, obj.polygon, None))
            except (json.JSONDecodeError, UnicodeDecodeError) as e:
                print(f"Ошибка: не удалось распарсить данные JSON из QR-кода: {e}")
                pass

    except Exception as e:
        print(f"Ошибка: Не удалось декодировать QR-код: {e}")

    return decoded_data_list


def recognize_selected_answers(image_gray, qr_data, show_marked_answers=True):
    # Получаем параметры из QR-кода
    question_count = qr_data['question_count']  # Количество вопросов
    option_count = qr_data['option_count']  # Количество вариантов ответов
    columns = qr_data['columns']  # Количество столбцов
    margin = qr_data['margin']  # Отступ от края контура
    question_spacing = qr_data['question_spacing']  # Расстояние между строками вопросов
    column_spacing = qr_data['column_spacing']  # Расстояние между столбцами вопросов
    border_thickness = qr_data['border_thickness']  # Толщина периметра
    border_margin = qr_data['border_margin']  # Отступ от края
    image_width = qr_data['image_width']  # Ширина изображения
    image_height = qr_data['image_height']  # Высота изображения

    # Выравниваем изображение
    alig_image = contour_alignment(image_gray, image_height, image_width)

    marked_test_image = alig_image.copy()  # Создаем копию изображения для отрисовки ответов
    # Применяем бинаризацию
    _, test_image = cv2.threshold(alig_image, 115, 255, cv2.THRESH_BINARY)

    # Параметры расположения
    option_spacing = 20  # Расстоние между вариантами ответа
    option_width = 30  # Ширина варианта ответа
    option_height = 30  # Высота варианта ответа

    # Начальные координаты (с учетом отступов и периметра)
    start_x = margin + border_thickness  # Учитываем отступ от периметра
    start_y = margin + border_thickness  # Учитываем отступ от периметра

    selected_answers = []

    rows = int(np.ceil(question_count / columns))  # Число строк

    # Переделанная логика для вопросов сверху вниз
    for i in range(question_count):
        col_index = i // rows  # Номер столбца
        row_index = i % rows  # Номер строки в столбце

        found_answer = False
        for j in range(option_count):
            # Координаты квадрата варианта ответа
            x = start_x + j * (option_width + option_spacing) + col_index * (
                    column_spacing + option_count * (option_width + option_spacing))
            y = start_y + row_index * question_spacing

            # Проверяем, закрашен ли квадрат
            color = test_image[y:y + option_height, x:x + option_width]

            if np.mean(color) / 255 <= 0.75:
                selected_answers.append(j+1)
                found_answer = True

                if show_marked_answers:
                    cv2.rectangle(marked_test_image, (x, y), (x + option_width, y + option_height), (0, 255, 0), 2)
                break
        if not found_answer:
            selected_answers.append(None)

    if show_marked_answers:
        print(f"Распознанные ответы: {selected_answers}")
        cv2.imshow("Test with Selected Answers", marked_test_image)
        cv2.waitKey(0)
        cv2.destroyAllWindows()

    return selected_answers


def checkTest(image_path, show_marked_answers=False):
    """Главная функция для обработки изображения."""
    # Считываем изображение
    image = image_path

    # Преобразуем в grayscale
    gray = cv2.cvtColor(image, cv2.COLOR_BGR2GRAY)

    # Находим QR код
    qr_code = find_qr_code(image_gray=gray)
    if qr_code is None:
        return
    # Применяем бинаризацию
    _, test_image = cv2.threshold(gray, 115, 255, cv2.THRESH_BINARY)
    # Извлекаем информацию из QR кода
    decoded_data_list = decode_qr_codes(contour_image=test_image)
    if not decoded_data_list:
        print("Ошибка: Не удалось декодировать ни одного QR-кода")
        return

    for qr_data, points, straight_qrcode in decoded_data_list:
        print(f"Информация из QR-кода: {qr_data}")
        # Записываем идентифицированные ответы
        selected_answers = recognize_selected_answers(image_gray=gray, qr_data=qr_data,
                                                      show_marked_answers=show_marked_answers)

    # Возвращаем распознанные ответы
    return selected_answers


if __name__ == "__main__":
    image_path = 'photo_2025-02-18_00-10-19.jpg'
    image = cv2.imread(image_path)
    a = checkTest(image_path=image, show_marked_answers=0)
    print(a)
