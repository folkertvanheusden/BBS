#! /usr/bin/python3

import ax25.socket
import os
import select
import socket
import sqlite3
import subprocess
import sys
import threading


mail_db = 'mail.db'

online = set()
online_lock = threading.Lock()


def send(s, str_):
    s.send(str_.encode('utf-8'))


def redirect_prog(cmd, socket):
    try:
        result = subprocess.run([cmd], capture_output=True, text=True).stdout
        for line in result.split('\n'):
            send(socket, line + '\n')

    except Exception as e:
        send(socket, f'Exception {e} while performing command, line number: {e.__traceback__.tb_lineno}\n')


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
                    msg = socket.recv(256)
                    send(to_socket, msg.decode('ascii') + '\n')

                elif e[0] == to_socket:
                    msg = to_socket.recv(256)
                    send(socket, msg.decode('ascii') + '\n')

        to_socket.close()
        send(socket, 'Disconnected\n')

    except Exception as e:
        send(socket, f'Exception {e} while connecting sockets, line number: {e.__traceback__.tb_lineno}\n')


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
        send(socket, f'Exception {e} while performing axcall, line number: {e.__traceback__.tb_lineno}\n')


def redirect_telnet(addr, socket):
    try:
        to_socket = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
        rc = to_socket.connect(addr)
        if rc != 0:
            to_socket.close()
            send(socket, f'Cannot connect to {callsign}: {os.strerror(rc)}\n')
            return

        redirect_sockets(to_socket, socket)

    except Exception as e:
        send(socket, f'Exception {e} while performing telnet, line number: {e.__traceback__.tb_lineno}\n')


def list_mail(call, socket):
    con = sqlite3.connect(mail_db)
    cur = con.cursor()
    try:
        cur.execute("SELECT id, `from`, `when` FROM mail WHERE `when` >= date('now','-1 month') AND `to`=? ORDER BY `when` DESC", (call,))
        for row in cur:
            send(socket, f'{row[0]}: {row[1]} - {row[2]}\n')
    except Exception as e:
        send(socket, f'Exception {e} while performing list_mail, line number: {e.__traceback__.tb_lineno}\n')
    cur.close()
    con.close()


def get_mail(nr, socket):
    con = sqlite3.connect(mail_db)
    cur = con.cursor()
    try:
        cur.execute("SELECT `from`, `when`, what FROM mail WHERE id=?", (nr,))
        row = cur.fetchone()
        send(socket, f'From: {row[0]} ({row[1]})\n')
        for line in row[2].split('\n'):
            send(socket, line + '\n')
    except Exception as e:
        send(socket, f'Exception {e} while performing get_mail, line number: {e.__traceback__.tb_lineno}\n')
    cur.close()
    con.close()


def get_line(socket):
    line = socket.recv(256)
    if line == None:
        return None

    line = line.decode('ascii').rstrip('\n').rstrip('\r').strip()
    return line


def send_mail(from_, to, msg, socket):
    con = sqlite3.connect(mail_db)
    cur = con.cursor()
    try:
        cur.execute('INSERT INTO mail(`id`, `from`, `to`, `when`, what) VALUES(NULL, ?, ?, CURRENT_TIMESTAMP, ?)', (from_, to, msg))
    except Exception as e:
        send(socket, f'Exception {e} while performing send_mail, line number: {e.__traceback__.tb_lineno}\n')
    cur.close()
    con.commit()
    con.close()


def list_online(s):
    global online_lock
    global online

    online_lock.acquire()
    temp = online
    online_lock.release()

    if len(temp) > 0:
        send(s, f'Currently on-line:\n')
        send(s, ', '.join(temp) + '\n')


def client_handler(s, call, is_tcp):
    global online_lock
    global online

    h_for_help = True

    send(s, f'This BBS software was written by Folkert van Heusden <folkert@vanheusden.com>\n\n')

    if is_tcp:
        while True:
            send(s, 'Please enter your call sign: ')
            call = get_line(s)
            if call is None:
                s.close()
                return
            call = call.upper()

            if len(call) > 0:
                break

    send(s, f'\nWelcome {call}!\n\n')

    online_lock.acquire()
    online.add(call)
    online_lock.release()
    list_online(s)

    menu = 0

    try:
        while True:
            if h_for_help:
                send(s, 'Enter "h" (+ enter) for help\n')
                h_for_help = False

            if menu == 0:
                send(s, 'main] ')
            elif menu == 1:
                send(s, 'msgs] ')
            else:
                send(s, 'internal error\n')
                break
            cmd = get_line(s)
            if cmd == None:
                break
            parts = cmd.split()
            if len(parts) == 0:
                h_for_help = True
                continue

            if menu == 0:
                if parts[0] == 'h':
                    send(s, 'm - mheard\n')
                    send(s, 'M - mail\n')
                    send(s, 'q - disconnect\n')
                    send(s, 'a - archie\n')
                    send(s, 'o - users on-line\n')
                    send(s, 'c callsign - connect to "callsign"\n')
                    send(s, 't host [port] - telnet\n')

                elif parts[0] == 'q':
                    break

                elif parts[0] == 'm':
                    redirect_prog('/usr/bin/mheard', s)

                elif parts[0] == 'o':
                    list_online(s)

                elif parts[0] == 'o':
                    list_online(s)

                elif parts[0] == 't' and len(parts) >= 2:
                    port = 23 if len(parts) == 2 else int(parts[2])
                    redirect_telnet((parts[1], port), s)
                    h_for_help = True

                elif parts[0] == 'c' and len(parts) == 2:
                    redirect_axcall(parts[1], s)

                elif parts[0] == 'a':
                    redirect_telnet(('localhost', 2030), s)

                else:
                    send(s, '???\n')
                    h_for_help = True

            elif menu == 1:
                if parts[0] == 'h':
                    send(s, 'l - list mail\n')
                    send(s, 'g x - show mail with number x\n')
                    send(s, 's - send mail\n')
                    send(s, 'p - previous menu\n')

                elif parts[0] == 'p':
                    menu = 0
                    h_for_help = True

                elif parts[0] == 'l':
                    list_mail(call, s)

                elif parts[0] == 'g' and len(parts) == 2:
                    get_mail(parts[1], s)

                elif parts[0] == 's':
                    send(s, 'To: ')
                    to = get_line(s)
                    if to == None:
                        continue
                    send(s, 'Message (max. 200 characters): ')
                    msg = get_line(s)
                    if msg == None:
                        continue
                    send_mail(call, to.upper(), msg, s)

                else:
                    send(s, '???\n')
                    h_for_help = True

    except Exception as e:
        send(s, f'Internal error: {e}, line number: {e.__traceback__.tb_lineno}\n')

    send(s, 'Bye bye\n\n')

    s.close()

    online_lock.acquire()
    online.remove(call)
    online_lock.release()

# create mail database
con = sqlite3.connect(mail_db)
try:
    cur = con.cursor()
    cur.execute('pragma journal_mode=wal')
    cur.execute('CREATE TABLE mail(`id` integer primary key, `from` text, `to` text, `when` int, what text)')
    cur.close()
    con.commit()
except Exception as e:
    print(e)
    pass
con.close()


if 'tcp' in sys.argv:
    server = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
    server.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
    server.bind(('0.0.0.0', 2300))

else:
    server = ax25.socket.Socket()
    server.bind('PI1GDA-1')

server.listen(128)

while True:
    client = server.accept()

    print(f'Connected to {client[1]}')

    t = threading.Thread(target=client_handler, args=(client[0], client[1], 'tcp' in sys.argv))
    t.daemon = True
    t.start()
