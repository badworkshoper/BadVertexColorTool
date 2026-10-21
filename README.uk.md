# BadVertexColorTool

[English version](README.md)

Швидкі й безпечні інструменти для Vertex Colors (Color Attributes) у Blender: fill, invert, правка каналів, фільтри, градієнти, bake, інтерактивний браш і перегляд одного каналу. Аддон пише лише в активний color attribute і лише у вибрані канали.

## Вимоги

- Blender 4.2 або новіший.
- Color attributes з доменом Point (вершини) або Face Corner, типу Byte або Float.

## Встановлення

- **Extension zip** (`bad_vertex_color_tool-<version>.zip`): Preferences > Get Extensions > меню-стрілка праворуч угорі > Install from Disk.
- **Legacy zip** (`BadVertexColorTool-<version>-legacy.zip`): Preferences > Add-ons > Install from Disk, потім увімкніть «BadVertexColorTool».

Інструменти знаходяться у 3D Viewport: Sidebar (N) > вкладка **BadVC**.

## Основні поняття

- **Канали R G B A**: рядок угорі панелі визначає, у які канали пишуть усі операції. Інші канали не змінюються.
- **Scope**: *All* — весь меш; *Selected* — лише вибрані елементи.
  - Edit Mode: вибрані вершини або грані (залежно від режиму виділення).
  - Vertex Paint: враховує маски Face / Vertex, якщо вони ввімкнені; без маски — весь меш.
  - Object Mode: весь меш.
- **Isolate** (кнопки R / G / B / A): показує один канал активного атрибута в градаціях сірого у в'юпорті. Дані меша не змінюються. Поки канал ізольований, редагування йде лише в нього. Повторний клік (або кнопка X) вимикає. Опція *Shading* додає легке затінення прев'ю; *Show in sRGB* показує значення з оберненою sRGB-гамою (sRGB в linear, середні тони темніші; лише відображення, збережені дані не змінюються). Поки канал ізольований, малювання, Apply і Gradient використовують Value замість Color.

## Панелі

- **Channel Values**: *Sample* зчитує середні значення каналів зачеплених елементів у слайдери; *Set All* записує всі чотири слайдери разом; *Set* біля слайдера пише лише цей канал.
- **Paint**
  - *Fill with Color* і *Fill with Value* (одне значення у вибрані канали).
  - *Invert*.
  - Режим **Mix / Add / Sub / Blur** зі спільною **Strength** (і Source для Mix/Add/Sub). *Apply* виконує один раз по scope; *Brush* використовує той самий режим і силу інтерактивно. Radius, Falloff, Spacing і Front Faces — налаштування браша.
- **Gradient** (згорнута): Source (значення або кольори), Easing, форма Linear / Radial (діє на всі три режими нижче).
  - *Axis*: X / Y / Z в Object або World просторі.
  - *Gesture*: *Draw Gradient*, потім протягніть у в'юпорті.
  - *Between Vertices*: виберіть рівно 2 вершини в Edit Mode або задайте групи Start / End; метод Linear або Geodesic. Radial росте від Start (точки чи групи) і досягає кінцевого значення в End.
- **Bake** (згорнута): Normal (Object / World, зі Swizzle каналів +-X/Y/Z у R/G/B/A; джерела: нормалі меша, proxy-об'єкт, spherical), AO, Random (по loose part / грані / вершині), Position (по осі або відстані). Рядок *Writes to* показує, які саме канали буде записано.
- **Adjust** (згорнута): Levels, Brightness / Contrast, Posterize, Clamp. Значення потім налаштовуються в *Adjust Last Operation* (F9).
- **Channel Transfer** (згорнута): *Within Attribute* — copy або swap одного каналу з іншим; *From Attribute* — copy або swap каналу чи повного кольору з іншого color attribute (домени й типи можуть відрізнятися).
- **Color Attribute** (згорнута): додати color attribute та переглянути назву, домен і тип активного.

## Керування Brush

Натисніть **Brush** у панелі Paint (працює у Vertex Paint та Object Mode).

| Клавіша | Дія |
|---------|-----|
| LMB drag | Малювати (один крок undo на штрих) |
| `[` / `]` | Менший / більший радіус |
| F | Інтерактивна зміна радіуса (LMB / F / Enter — підтвердити, Esc — скасувати) |
| Shift+F | Інтерактивна зміна сили |
| Shift (утримувати) | Blur замість поточного режиму |
| Ctrl (утримувати) | Інверсія режиму (Add стає Sub тощо) |
| Ctrl+Z | Завершити сесію й скасувати останній штрих |
| Esc / RMB / Enter / Ctrl+Tab | Вийти з браша |

Колесо миші та MMB навігують в'юпорт як зазвичай.

## Керування Gradient gesture

Натисніть *Draw Gradient*, потім протягніть LMB у в'юпорті від початкової до кінцевої точки; відпустіть — градієнт застосується. Утримуйте **Shift** під час перетягування для прилипання напрямку. **Esc** або **RMB** — скасувати. Надто короткі перетягування ігноруються.

## Поради та обмеження

- Якщо сесія браша почалась в Edit Mode і ви натиснули Ctrl+Z, об'єкт лишається в Object Mode.
- У Vertex Paint поруч із курсором аддона видно рідне червоне коло пензля Blender.
- Фільтр *Front Faces* враховує лише нормаль вершини (без перевірки оклюзії).
- Isolate в Edit Mode показує останні синхронізовані дані; щоб оновити, вийдіть і зайдіть в Edit Mode.
- AO для об'єктів із модифікаторами кидає промені з вершин базового меша.

## Ліцензія

GPL-3.0-or-later.
