from datetime import datetime
from time import sleep
from socket import *
from threading import Thread
from queue import Queue
from json import load
import struct
from tkinter import PhotoImage, Spinbox, StringVar, Tk, Frame, Label, Button, Toplevel, Canvas
from tkinter.ttk import Notebook, Combobox, Scrollbar
from tkinter.scrolledtext import ScrolledText

ACC_PORT, SERVER_PORT, COMMANDS, MSG_TYPE, CAR_LOCATION, SESSION_PHASE, SESSION_TYPE, BROADCASTING_EVENT_TYPE = load(
    open('./consts.json')).values()

game_server = socket(type=SOCK_DGRAM)
game_server.bind(('localhost', SERVER_PORT))
IP = "127.0.0.1"
PROTOCOL_VERSION = 4
DISPLAY_NAME = "race_control"
CONN_PW = ""
COMMAND_PW = ""
MS_UPDATE_INTERVAL = 100
THRESHOLD = 5000

ids_to_cars = {}
timestamp_accidents = {}
event_queue = Queue()
listed_accidents = []
listed_vsc = []

# region utils

# write string to bytes


def write_string(string, buffer):
    buffer.append(len(bytearray(string, 'utf-8')))
    buffer.append(0)
    buffer.extend(string.encode('utf-8'))

# read 1 byte int


def read_small_int(data):
    return struct.unpack('b', bytes([data]))[0]

# read 2 bytes int


def read_int(data):
    return struct.unpack('H', data)[0]

# read 4 bytes int


def read_big_int(data):
    return struct.unpack('i', data)[0]

# read string from bytes


def read_string(data):
    length = read_int(data[0:2])
    return data[2:(2 + length)].decode('utf-8')

# get bytes after a string


def get_bytes_after_string(data):
    length = read_int(data[0:2])
    return data[(2 + length):]


def get_car_number(id):
    return ids_to_cars[str(id)]['number']


def get_car_lap(id):
    return ids_to_cars[str(id)]['lap']


def get_car_last(id):
    return ids_to_cars[str(id)]['last']


def get_car_location(id):
    return ids_to_cars[str(id)]['location']


def set_car_number(id, number):
    ids_to_cars[str(id)]['number'] = number


def set_car_last(id, last):
    ids_to_cars[str(id)]['last'] = last


def set_entry_list(data):
    count = read_int(data[4:6])
    ids = data[6:]
    for i in range(count):
        ids_to_cars[str(read_int(ids[i * 2:(i + 1) * 2]))
                    ] = {'position': None, 'number': None, 'lap': 0, 'last': 0, 'time_over_vsc': 0}


def update_car_info(id, lap, location, kmh=None):
    global vsc_kmh, vsc_deployed
    ids_to_cars[str(id)]['lap'] = lap
    ids_to_cars[str(id)]['location'] = location
    if vsc_deployed:
        if kmh > vsc_kmh:
            timestamp = datetime.now().timestamp() * 1000
            if 'last_vsc' in ids_to_cars[str(id)]:
                ids_to_cars[str(id)]['time_over_vsc'] = ids_to_cars[str(id)]['time_over_vsc'] + (timestamp -
                                                                                                 ids_to_cars[str(id)]['last_vsc']) / 1000
                ids_to_cars[str(id)]['last_vsc'] = timestamp
                filtered = list(filter(
                    lambda entry: entry[0] == ids_to_cars[str(id)]['number'], listed_vsc))
                if len(filtered) > 0:
                    listed_vsc[listed_vsc.index(
                        filtered[0])] = (ids_to_cars[str(id)]['number'], ids_to_cars[str(id)]['time_over_vsc'])
                else:
                    listed_vsc.append(
                        (ids_to_cars[str(id)]['number'], ids_to_cars[str(id)]['time_over_vsc']))
            else:
                ids_to_cars[str(id)]['kmh'] = kmh
                ids_to_cars[str(id)]['last_vsc'] = timestamp
        elif 'last_vsc' in ids_to_cars[str(id)]:
            del ids_to_cars[str(id)]['last_vsc']

# send request to get updated entry list


def request_entry_list(conn_id):
    msg = bytearray(b'\x0a')
    msg.append(conn_id)
    msg.append(0)
    msg.append(0)
    msg.append(0)
    game_server.sendto(msg, (IP, ACC_PORT))
# endregion

# region main functions


def connect():
    msg = bytearray()
    msg.append(COMMANDS['REQUEST_CONN'])
    msg.append(PROTOCOL_VERSION)
    write_string(DISPLAY_NAME, msg)
    write_string(CONN_PW, msg)
    msg.append(MS_UPDATE_INTERVAL)
    msg.append(0)
    msg.append(0)
    msg.append(0)
    write_string(COMMAND_PW, msg)
    game_server.sendto(msg, (IP, ACC_PORT))
    data, _ = game_server.recvfrom(2 * 1024 * 1024)
    event_queue.put_nowait(data)


def disconnect():
    msg = bytearray()
    msg.append(COMMANDS['UNREGISTER_COMMAND_APPLICATION'])
    # print('Disconnected')
    game_server.sendto(msg, (IP, ACC_PORT))
    game_server.close()
    window.destroy()

# process data coming from ACC


def process_events():
    global session
    conn_id = None
    info_available = False
    while True:
        data = event_queue.get()
        try:
            if data[0] == MSG_TYPE['REGISTRATION_RESULT'] and not conn_id:
                conn_id = read_big_int(data[1:5])
                #print(f'Connected with id {conn_id}')
                request_entry_list(conn_id)
                window.winfo_children()[0].config(text='Connected')
                event_queue.task_done()

            elif data[0] == MSG_TYPE['REALTIME_UPDATE']:
                sess = SESSION_TYPE[str(read_small_int(data[5]))]
                if not session or session != sess:
                    session = sess
                    #print(f'\nSession: {session}\n')
                    timestamp_accidents.clear()
                    event_queue.task_done()

            elif data[0] == MSG_TYPE['REALTIME_CAR_UPDATE'] and info_available:
                car_id = read_int(data[1:3])
                location = CAR_LOCATION[read_small_int(data[19])]
                lap = read_int(data[32:34]) + 1
                kmh = read_int(data[20:22])
                update_car_info(car_id, lap, location, kmh)
                event_queue.task_done()

            elif data[0] == MSG_TYPE['ENTRY_LIST']:
                set_entry_list(data[1:])
                info_available = True
                event_queue.task_done()

            elif data[0] == MSG_TYPE['ENTRY_LIST_CAR']:
                id = read_int(data[1:3])
                data = get_bytes_after_string(data[4:])
                number = read_big_int(data[:4])
                set_car_number(id, number)
                event_queue.task_done()

            elif data[0] == MSG_TYPE['BROADCASTING_EVENT'] and info_available:
                event_type = BROADCASTING_EVENT_TYPE[read_small_int(data[1])]
                if event_type == 'Accident':
                    data = get_bytes_after_string(data[2:])
                    ms = read_big_int(data[:4])
                    car_id = read_big_int(data[4:])
                    if get_car_location(car_id) == 'Track':
                        car_no = get_car_number(car_id)
                        if not car_no:
                            raise KeyError
                        if ms - get_car_last(car_id) >= THRESHOLD:
                            closest = None
                            timestamps = list(timestamp_accidents.keys())
                            closest_sorted = sorted(list(map(lambda timestamp: (timestamp, abs(
                                int(timestamp) - ms)), timestamps)), key=lambda x: x[1])
                            if len(closest_sorted) > 0 and closest_sorted[0][1] <= 1000:
                                closest = closest_sorted[0][0]
                            if closest:
                                if car_no not in timestamp_accidents[closest]['cars']:
                                    timestamp_accidents[closest]['cars'].append(
                                        car_no)
                            else:
                                timestamp_accidents[str(ms)] = {
                                    'lap': get_car_lap(car_id),
                                    'cars': [car_no]
                                }
                        set_car_last(car_id, ms)
                        event_queue.task_done()
        except KeyError:
            request_entry_list(conn_id)
            event_queue.put(data)
            event_queue.task_done()

# render UI accidents tab


def update_accidents_table():
    for widget in accidents_tab.winfo_children():
        widget.destroy()
    headers = ['Cars', 'Lap', 'Session', '', '']

    scrollbar = Scrollbar(accidents_tab, orient='vertical')
    scrollbar.grid(row=0, column=1, sticky='ns')

    canvas = Canvas(accidents_tab,
                    yscrollcommand=scrollbar.set)
    canvas.create_image(0, 0, anchor='ne')
    canvas['scrollregion'] = (0, 0, 0, (len(listed_accidents) + 1) * 30)
    canvas['width'] = 565
    canvas['height'] = 370
    canvas.grid(row=0, column=0)

    scrollbar.config(command=canvas.yview)
    canvas.config(scrollregion=canvas.bbox("all"))

    table = Frame(canvas)

    for j, column in enumerate(headers):
        label = Label(table, text=column, width=15,
                      height=2, font='Helvetica 8 bold')
        label.grid(row=0, column=j,
                   sticky="nsew", padx=1, pady=1)
        table.grid_columnconfigure(j, weight=1)
    for i, row in enumerate(listed_accidents):
        for j, column in enumerate(row):
            label = Label(table, text=column,
                          bg='Light Gray', height=1)
            label.grid(row=i + 1, column=j,
                       sticky="nsew", padx=1, pady=1)
            table.grid_columnconfigure(j, weight=1)
            if j == 2:
                dismiss_button = Button(table, text="Racing Incident",
                                        bg='medium sea green', width=5, command=lambda row=i: dismiss_accident(row))
                penalty_button = Button(table, text="Penalty",
                                        bg='indian red', width=5, command=lambda row=i: add_penalty(row))

                dismiss_button.grid(row=i + 1, column=j + 1,
                                    padx=1, pady=1, sticky="nsew")
                penalty_button.grid(row=i + 1, column=j + 2,
                                    padx=1, pady=1, sticky="nsew")
                table.grid_columnconfigure(j + 1, weight=1)

    canvas.create_window((0, 0), window=table, anchor='nw')


def set_vsc_details(button, kmh):
    global vsc_kmh, vsc_deployed
    if not vsc_deployed:
        button['bg'] = 'Yellow'
        vsc_deployed = True
        vsc_kmh = int(kmh)
    else:
        button['bg'] = 'Gray'
        vsc_deployed = False
        for car in ids_to_cars:
            if 'last_vsc' in ids_to_cars[car]:
                del ids_to_cars[car]['last_vsc']
        listed_vsc.sort(key=lambda x: x[1], reverse=True)
        update_vsc_table()

# render UI VSC tab


def update_vsc_table():
    global vsc_kmh
    for widget in vsc_tab.winfo_children():
        widget.destroy()

    headers = ['Car', 'Time Over Limit', '', '']

    scrollbar = Scrollbar(vsc_tab, orient='vertical')
    scrollbar.grid(row=0, column=1, sticky='ns')

    canvas = Canvas(vsc_tab,
                    yscrollcommand=scrollbar.set)
    canvas.create_image(0, 0, anchor='ne')
    canvas['scrollregion'] = (0, 0, 0, (len(listed_vsc) + 1) * 30)
    canvas['width'] = 565
    canvas['height'] = 370
    canvas.grid(row=0, column=0)

    scrollbar.config(command=canvas.yview)
    canvas.config(scrollregion=canvas.bbox("all"))

    table = Frame(canvas)

    vsc_label = Label(table, text='VSC speed', width=15,
                      height=2, font='Helvetica 8 bold')
    cur_vsc_speed = StringVar(table)
    cur_vsc_speed.set(vsc_kmh)
    vsc_speed = Spinbox(table, from_=50, to=200, increment=10,
                        state='readonly', width=15, textvariable=cur_vsc_speed)
    vsc_button = Button(table, text='On/Off', bg='Gray',
                        command=lambda: set_vsc_details(vsc_button, vsc_speed.get()))
    vsc_label.grid(row=0, column=4,
                   padx=1, pady=1, sticky="nsew")
    vsc_speed.grid(row=1, column=4,
                   padx=1, pady=1, sticky="nsew")
    vsc_button.grid(row=2, column=4,
                    padx=1, pady=1, sticky="nsew")
    table.grid_columnconfigure(0, weight=1)
    table.grid_columnconfigure(1, weight=1)
    table.grid_columnconfigure(2, weight=1)

    for j, column in enumerate(headers):
        label = Label(table, text=column, width=15,
                      height=2, font='Helvetica 8 bold')
        label.grid(row=0, column=j,
                   sticky="nsew", padx=1, pady=1)
        table.grid_columnconfigure(j, weight=1)
    for i, row in enumerate(listed_vsc):
        for j, column in enumerate(row):
            label = Label(table, text=column if j == 0 else f"{float(column):.2f}",
                          bg='Light Gray')
            label.grid(row=i + 1, column=j,
                       sticky="nsew", padx=1, pady=1)
            table.grid_columnconfigure(j, weight=1)
            if j == 1:
                dismiss_button = Button(table, text="Dismiss",
                                        bg='medium sea green', width=5, command=lambda row=i: dismiss_vsc_accident(row))
                penalty_button = Button(table, text="Penalty",
                                        bg='indian red', width=5, command=lambda row=i: add_vsc_penalty(row))

                dismiss_button.grid(row=i + 1, column=j + 1,
                                    padx=1, pady=1, sticky="nsew")
                penalty_button.grid(row=i + 1, column=j + 2,
                                    padx=1, pady=1, sticky="nsew")
                table.grid_columnconfigure(j + 1, weight=1)

    canvas.create_window((0, 0), window=table, anchor='nw')


def add_penalty(index):
    global listed_accidents
    penalties = ['Time', 'DT', 'SG10', 'SG30']
    popup = Toplevel(accidents_tab)

    x = window.winfo_x()
    y = window.winfo_y()
    popup.geometry("+%d+%d" % (x + window.winfo_width() //
                   3.5, y + window.winfo_height() //
                   3))

    dialog = Frame(popup, padx=20, pady=10)
    dialog.pack(fill='both', anchor='center')

    label = Label(dialog, text='Penalty')
    label.pack(fill='both', side='left')

    penalty = Combobox(dialog, values=penalties, state="readonly")
    penalty.current(0)
    penalty.pack(fill='both', side='left')

    seconds = Spinbox(dialog, from_=5, to=100, increment=5,
                      width=5, state='readonly')
    seconds.pack(fill='both', side='left', padx=2)

    buttons = Frame(popup, padx=20, pady=5)
    buttons.pack(side='bottom')

    label = Label(dialog, text='To')
    label.pack(fill='both', side='left')

    involved_cars = listed_accidents[index][0].split(', ')
    cars = Combobox(dialog, values=involved_cars,
                    width=5)
    cars.current(0)
    cars.pack(fill='both', side='right', padx=2)

    confirm = Button(buttons, text='Confirm',
                     command=lambda: log_accident(index, popup, f'Penalty : {"+"+seconds.get()+"s" if penalty.get()=="Time" else penalty.get()} to #{cars.get()}'))
    confirm.pack(fill='both', side='left', padx=2)
    suggestion = Button(buttons, text='Get commands',
                        command=lambda: suggest_penalty(index, seconds.get(), penalty.get(), cars.get()))
    suggestion.pack(fill='both', side='left', padx=2)
    cancel = Button(buttons, text='Cancel',
                    command=popup.destroy)
    cancel.pack(fill='both', side='right', padx=2)

# suggest penalty commands to the user


def suggest_penalty(index, seconds, penalty, car):
    penalty_str = ""
    if penalty == 'Time':
        secs = int(seconds) // 15
        reminder = int(seconds) % 15
        if secs:
            for _ in range(secs):
                penalty_str += f"\\tp15 {car}\n"
        if reminder:
            for _ in range(reminder // 5):
                penalty_str += f"\\tp5 {car}\n"
    else:
        penalty_str = f"\\{penalty.lower()} {car}"

    popup = Toplevel(window)

    x = window.winfo_x()
    y = window.winfo_y()
    popup.geometry("+%d+%d" % (x + window.winfo_width() //
                   3.5, y + window.winfo_height() //
                   3))

    dialog = Frame(popup, padx=20, pady=10, width=200)
    dialog.pack(fill='both', anchor='center')

    label = Label(dialog, text='Copy this commands as admin')
    label.pack(fill='both', side='top')

    text = ScrolledText(dialog, width=10, height=5)
    text.insert('end', penalty_str)
    text.pack(fill='both', side='bottom')

    buttons = Frame(popup, padx=20, pady=5)
    buttons.pack(side='bottom')

    confirm = Button(buttons, text='Confirm',
                     command=lambda: log_accident(index, popup, f'Penalty : {"+"+seconds+"s" if penalty=="Time" else penalty} to #{car}'))
    confirm.pack(fill='both', side='left', padx=2)
    cancel = Button(buttons, text='Cancel',
                    command=popup.destroy)
    cancel.pack(fill='both', side='right', padx=2)


def add_vsc_penalty(index):
    global listed_vsc
    penalties = ['Time', 'DT', 'SG10', 'SG30']
    popup = Toplevel(vsc_tab)

    x = window.winfo_x()
    y = window.winfo_y()
    popup.geometry("+%d+%d" % (x + window.winfo_width() //
                   3.5, y + window.winfo_height() //
                   3))

    dialog = Frame(popup, padx=20, pady=10)
    dialog.pack(fill='both', anchor='center')

    label = Label(dialog, text='Penalty')
    label.pack(fill='both', side='left')

    penalty = Combobox(dialog, values=penalties, state="readonly")
    penalty.current(0)
    penalty.pack(fill='both', side='left')

    value = StringVar(popup)
    # round to nearest 5
    value.set(int(5 * round(float(listed_vsc[index][1]) / 5)))
    seconds = Spinbox(dialog, from_=5, to=100, increment=5,
                      width=5, state='readonly', textvariable=value)
    seconds.pack(fill='both', side='right', padx=2)

    buttons = Frame(popup, padx=20, pady=5)
    buttons.pack(side='bottom')

    confirm = Button(buttons, text='Confirm',
                     command=lambda: log_vsc(index, popup, f'Penalty : {"+"+seconds.get()+"s" if cb.get()=="Time" else cb.get()}'))
    confirm.pack(fill='both', side='left', padx=2)
    suggestion = Button(buttons, text='Get commands',
                        command=lambda: suggest_vsc_penalty(index, seconds.get(), penalty.get()))
    suggestion.pack(fill='both', side='left', padx=2)
    cancel = Button(buttons, text='Cancel',
                    command=popup.destroy)
    cancel.pack(fill='both', side='right', padx=2)

# update accidents list from ids_to_cars


def suggest_vsc_penalty(index, seconds, penalty):
    car = int(listed_vsc[index][0])
    penalty_str = ""
    if penalty == 'Time':
        secs = int(seconds) // 15
        reminder = int(seconds) % 15
        if secs:
            for _ in range(secs):
                penalty_str += f"\\tp15 {car}\n"
        if reminder:
            for _ in range(reminder // 5):
                penalty_str += f"\\tp5 {car}\n"
    else:
        penalty_str = f"\\{penalty.lower()} {car}"

    popup = Toplevel(window)

    x = window.winfo_x()
    y = window.winfo_y()
    popup.geometry("+%d+%d" % (x + window.winfo_width() //
                   3.5, y + window.winfo_height() //
                   3))

    dialog = Frame(popup, padx=20, pady=10, width=200)
    dialog.pack(fill='both', anchor='center')

    label = Label(dialog, text='Copy this commands as admin')
    label.pack(fill='both', side='top')

    text = ScrolledText(dialog, width=10, height=5)
    text.insert('end', penalty_str)
    text.pack(fill='both', side='bottom')

    buttons = Frame(popup, padx=20, pady=5)
    buttons.pack(side='bottom')

    confirm = Button(buttons, text='Confirm',
                     command=lambda: log_vsc(index, popup, f'Penalty : {"+"+seconds+"s" if penalty=="Time" else penalty} to #{car}'))
    confirm.pack(fill='both', side='left', padx=2)
    cancel = Button(buttons, text='Cancel',
                    command=popup.destroy)
    cancel.pack(fill='both', side='right', padx=2)


def spot_accidents():
    while True:
        to_remove = []
        items = list(timestamp_accidents.items())
        for timestamp, data in items:
            listed_accidents.append(
                (', '.join([f'{car}' for car in data['cars']]), data['lap'], session))
            to_remove.append(timestamp)
        if len(items) > 0:
            update_accidents_table()

        for timestamp in to_remove:
            timestamp_accidents.pop(timestamp)
        sleep(THRESHOLD // 1000)


def dismiss_accident(index):
    listed_accidents.pop(index)
    update_accidents_table()
    #print(f'Racing Incident')


def dismiss_vsc_accident(index):
    listed_vsc.pop(index)
    update_vsc_table()


def log_accident(index, box, message):
    # print(message)
    listed_accidents.pop(index)
    update_accidents_table()
    box.destroy()


def log_vsc(index, box, message):
    # print(message)
    listed_vsc.pop(index)
    update_vsc_table()
    box.destroy()

# retrieve data from ACC


def get_data():
    while True:
        try:
            data, _ = game_server.recvfrom(2 * 1024 * 1024)
            event_queue.put_nowait(data)
        except:
            exit()

# create main window


def create_gui():

    window = Tk()
    window.title("ACC Race Control")
    window.iconphoto(True, PhotoImage(file='flag.png'))
    window.geometry("600x400")
    window.wm_resizable(False, False)
    window.maxsize(height=0, width=590)

    conn_label = Label(window, text="Connecting...")
    conn_label.pack(anchor='ne')

    tablayout = Notebook(window)

    # tab1
    accidents_tab = Frame(tablayout)

    tablayout.add(accidents_tab, text='Accidents')

    # tab2
    vsc_tab = Frame(tablayout)

    tablayout.add(vsc_tab, text='VSC')

    tablayout.pack(fill="both")

    window.protocol("WM_DELETE_WINDOW", disconnect)

    return window, accidents_tab, vsc_tab
# endregion


session = None
vsc_deployed = False
vsc_kmh = 50


main_thread = Thread(target=get_data, daemon=True)
events_thread = Thread(target=process_events, daemon=True)
accidents_thread = Thread(target=spot_accidents, daemon=True)

if __name__ == '__main__':
    window, accidents_tab, vsc_tab = create_gui()

    events_thread.start()
    accidents_thread.start()
    main_thread.start()

    connect()

    window.after(100, update_accidents_table)
    window.after(100, update_vsc_table)
    window.mainloop()
