#! /usr/bin/python3

import ax25.socket
import os
import select
import subprocess
import threading

def send(s, str_):
    s.send(str_.encode('ascii'))


def redirect_prog(cmd, socket):
    try:
        result = subprocess.run([cmd], capture_output=True, text=True).stdout
        for line in result.split('\n'):
            send(socket, line + '\n')

    except Exception as e:
        send(socket, f'Exception {e} while performing command')


def redirect_sockets(to_socket, socket):
    try:
        p = select.poll()
        p.register(socket, select.POLLIN)
        p.register(to_socket, select.POLLIN)

        while True:
            rc = p.poll(86400)
            if len(rc) == 0:
                send(socket, 'timeout\n')
                break

            for e in rc:
                if e[0] == socket:
                    msg = socket.recv()
                    send(to_socket, msg.decode('ascii') + '\n')

                elif e[0] == to_socket:
                    msg = to_socket.recv()
                    send(socket, msg.decode('ascii') + '\n')

        to_socket.close()
        send(socket, 'Disconnected\n')

    except Exception as e:
        send(socket, f'Exception {e} while performing axcall')

def redirect_axcall(callsign, socket):
    try:
        to_socket = ax25.socket.Socket()
        rc = to_socket.connect_ex(callsign)
        if rc != 0:
            to_socket.close()
            send(socket, f'Cannot connect to {callsign}: {os.strerror(rc)}\n')
            return

        redirect_sockets(to_socket, socket)

    except Exception as e:
        send(socket, f'Exception {e} while performing axcall')

def client_handler(s, call):
    h_for_help = True

    try:
        while True:
            if h_for_help:
                send(s, 'Enter "h" (+ enter) for help\n')
                h_for_help = False

            cmd = s.recv()
            if cmd == None:
                break

            cmd = cmd.rstrip('\n').rstrip('\r').strip()
            parts = cmd.split()

            if parts[0] == 'h':
                send(s, 'm - mheard\n')
                send(s, 'q - disconnect\n')
                send(s, 'a - archie\n')
                send(s, 'c callsign - connect to "callsign"\n')

            elif parts[0] == 'q':
                break

            elif parts[0] == 'm':
                redirect_prog('/usr/bin/mheard', s)

            elif parts[0] == 'c' and len(parts) == 2:
                redirect_axcall(parts[1], s)

            else:
                send(s, '???\n')
                h_for_help = True

    except Exception as e:
        send(s, f'Internal error: {e}')

    send(s, 'Bye bye')

    s.close()


server = ax25.socket.Socket()
server.bind('PI1GDA-1')
server.listen(128)

while True:
    client = server.accept()

    print(f'Connected to {client[1]}')

    t = threading.Thread(target=client_handler, args=(client[0], client[1],))
    t.daemon = True
    t.start()
