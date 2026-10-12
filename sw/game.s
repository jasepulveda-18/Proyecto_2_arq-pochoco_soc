# Proyecto 2 - Juego de reflejos para Espino Core
#
# Flujo:
#   1. El jugador presiona cualquier boton para iniciar la partida.
#   2. Cada ronda enciende los cuatro LEDs durante tres segundos.
#   3. Se selecciona un LED usando una semilla dependiente del tiempo humano.
#   4. Se mide la respuesta desde que aparece el LED objetivo.
#   5. Una respuesta correcta se muestra en decimas de segundo.
#   6. Una respuesta incorrecta muestra EE y reinicia la misma ronda.
#   7. Despues del decimo acierto, su tiempo queda visible hasta que el
#      jugador presiona y suelta cualquier boton; entonces se muestra el
#      promedio.
#
# Mapa de perifericos:
#   0x80000000: displays de 7 segmentos (BCD: decenas | unidades)
#   0x80000004: LEDs
#   0x80000008: botones
#   0x8000000C: contador de ciclos de 32 bits
#
# Constantes de tiempo para el reloj de 25 MHz de la Go Board:
#   3 segundos = 75,000,000 ciclos
#   1 segundo  = 25,000,000 ciclos
#   0.1 s      =  2,500,000 ciclos
#
# Registros persistentes:
#   x2 = base de perifericos
#   x3 = direccion displays
#   x4 = direccion LEDs
#   x5 = direccion botones
#   x6 = direccion contador
#   x7 = cantidad de respuestas correctas
#   x8 = suma de tiempos correctos, en decimas
#   x9 = semilla pseudoaleatoria
# Los registros x10-x15 se reutilizan como temporales.

.section .text
.global _start

_start:
    # Direcciones de los perifericos.
    lui  x2, 0x80000
    addi x3, x2, 0
    addi x4, x2, 4
    addi x5, x2, 8
    addi x6, x2, 12

    # Estado inicial.
    addi x7, x0, 0           # respuestas correctas = 0
    addi x8, x0, 0           # suma de tiempos = 0
    addi x10, x0, 136        # 0x88 indica que el programa arranco
    sw   x10, 0(x3)          # listo: esperando una pulsacion nueva
    sw   x0, 0(x4)           # LEDs apagados

    # El instante humano del primer boton entrega una semilla que cambia
    # entre partidas; asi la secuencia no es fija despues de cada encendido.
    # Primero se exige que todos los botones esten sueltos, para que una pulsacion
    # mantenida durante la programacion no inicie la partida accidentalmente.
wait_start_idle:
    lw   x10, 0(x5)
    bne  x10, x0, wait_start_idle

wait_start_press:
    lw   x10, 0(x5)
    beq  x10, x0, wait_start_press
    lw   x9, 0(x6)

wait_start_release:
    lw   x10, 0(x5)
    bne  x10, x0, wait_start_release
    sw   x0, 0(x3)           # borrar 88 antes de la primera ronda

round_start:
    # Cuatro LEDs encendidos durante al menos tres segundos.
    addi x10, x0, 15
    sw   x10, 0(x4)
    lw   x10, 0(x6)          # ciclo inicial de la espera

    # x11 = 75,000,000 = 0x047868C0.
    lui  x11, 0x04787
    addi x11, x11, -1856

wait_three_seconds:
    lw   x12, 0(x6)
    sub  x13, x12, x10
    bltu x13, x11, wait_three_seconds

    # Mezclar la semilla anterior, el ciclo actual y la ronda.
    # El tiempo de respuesta humano de las rondas anteriores cambia x12.
    add  x9, x9, x12
    add  x9, x9, x7
    addi x9, x9, 1
    andi x10, x9, 3          # indice objetivo: 0, 1, 2 o 3

    # Espino no implementa shifts, por eso se elige 1, 2, 4 u 8
    # mediante branches en vez de calcular 1 << indice.
    beq  x10, x0, target_led_1
    addi x11, x0, 1
    beq  x10, x11, target_led_2
    addi x11, x0, 2
    beq  x10, x11, target_led_4
    addi x11, x0, 8
    jal  x0, show_target

target_led_1:
    addi x11, x0, 1
    jal  x0, show_target

target_led_2:
    addi x11, x0, 2
    jal  x0, show_target

target_led_4:
    addi x11, x0, 4

show_target:
    sw   x11, 0(x4)          # encender solamente el LED objetivo
    lw   x12, 0(x6)          # inicio de medicion de la respuesta

wait_for_button:
    lw   x13, 0(x5)
    beq  x13, x0, wait_for_button
    lw   x14, 0(x6)          # instante de la pulsacion detectada

    # Se exige exactamente el boton asociado al LED objetivo.
    bne  x13, x11, wrong_button

correct_button:
    # Convertir ciclos a decimas mediante restas repetidas.
    sub  x15, x14, x12       # ciclos de respuesta

    # x10 = 2,500,000 ciclos por decima = 0x002625A0.
    lui  x10, 0x00262
    addi x10, x10, 1440
    addi x12, x0, 0          # tiempo en decimas

cycles_to_tenths:
    bltu x15, x10, time_converted
    sub  x15, x15, x10
    addi x12, x12, 1
    jal  x0, cycles_to_tenths

time_converted:
    add  x8, x8, x12         # acumular tiempo correcto
    addi x7, x7, 1           # una respuesta correcta mas
    jal  x1, display_tenths

    addi x10, x0, 10
    beq  x7, x10, wait_tenth_release

wait_correct_release:
    lw   x10, 0(x5)
    bne  x10, x0, wait_correct_release
    jal  x0, round_start

    # El boton del decimo acierto todavia puede estar presionado. Primero se
    # exige soltarlo. El tiempo del decimo intento queda visible mientras se
    # espera una nueva pulsacion deliberada para mostrar el promedio.
wait_tenth_release:
    sw   x0, 0(x4)           # apagar el LED objetivo
    lw   x10, 0(x5)
    bne  x10, x0, wait_tenth_release

wait_average_press:
    lw   x10, 0(x5)
    beq  x10, x0, wait_average_press

wait_average_release:
    lw   x10, 0(x5)
    bne  x10, x0, wait_average_release
    jal  x0, calculate_average

wrong_button:
    # EE indica error en ambos displays. No se cambia x7 ni x8.
    addi x10, x0, 238        # 0xEE
    sw   x10, 0(x3)
    sw   x0, 0(x4)

wait_wrong_release:
    lw   x10, 0(x5)
    bne  x10, x0, wait_wrong_release

    # Mantener EE durante un segundo antes de reiniciar la ronda.
    lw   x10, 0(x6)
    lui  x11, 0x017D8        # 25,000,000 = 0x017D7840
    addi x11, x11, -1984

wait_error_second:
    lw   x12, 0(x6)
    sub  x13, x12, x10
    bltu x13, x11, wait_error_second
    jal  x0, round_start

calculate_average:
    # Promedio entero en decimas: suma / 10, truncando el residuo.
    add  x15, x8, x0
    addi x12, x0, 0
    addi x10, x0, 10

average_loop:
    bltu x15, x10, average_ready
    addi x15, x15, -10
    addi x12, x12, 1
    jal  x0, average_loop

average_ready:
    jal  x1, display_tenths
    sw   x0, 0(x4)

game_finished:
    jal  x0, game_finished


# display_tenths
# Entrada: x12 = valor entero en decimas.
# Salida: dos digitos BCD en los displays. Valores mayores a 99 se saturan.
# Retorno: direccion guardada en x1 por JAL.
display_tenths:
    addi x13, x0, 100
    bltu x12, x13, split_decimal_digits
    addi x12, x0, 99

split_decimal_digits:
    addi x14, x0, 0          # decenas
    add  x15, x12, x0        # unidades antes de dividir por 10
    addi x13, x0, 10

decimal_loop:
    bltu x15, x13, pack_bcd
    addi x15, x15, -10
    addi x14, x14, 1
    jal  x0, decimal_loop

pack_bcd:
    # Multiplicar decenas por 16 sin usar shifts: cuatro duplicaciones.
    add  x10, x14, x14       # *2
    add  x10, x10, x10       # *4
    add  x10, x10, x10       # *8
    add  x10, x10, x10       # *16
    add  x10, x10, x15       # BCD = decenas*16 + unidades
    sw   x10, 0(x3)
    jalr x0, 0(x1)
