#!/usr/bin/env python
"""
Stand alone stream viewer uses pyqtgraph to display the images.
"""
import argparse
import ctypes
import multiprocessing as mp
import numpy as np
import zmq
import json


import pyqtgraph as pg
from pyqtgraph.Qt import QtCore, QtGui, QtWidgets
from pyqtgraph.dockarea import DockArea, Dock

from PySide6.QtWidgets import QGraphicsEllipseItem, QGraphicsRectItem
from PySide6.QtCore import QRectF


endpoints = ['tcp://129.129.202.53:30000', 'tcp://129.129.202.53:30001']
n_modules = len(endpoints)

#Configuration
nrow = 512
ncol = 1024
dt = np.uint16
timeout_ms = 100

def ctypes_dt(dt):
    if dt == np.uint16:
        return ctypes.c_uint16
    elif dt == np.float32:
        return ctypes.c_float
    else:
        raise ValueError("Unsupported data type")
    



pg.setConfigOptions(imageAxisOrder='row-major')
pg.mkQApp()

app = pg.mkQApp("DockArea Example")
win = QtWidgets.QMainWindow()
win.setWindowTitle('Jungfrau')
area = DockArea()
win.setCentralWidget(area)
win.resize(1000,500)
d1 = Dock("Image", size=(1000, 250))
area.addDock(d1, 'top')
w1 = pg.GraphicsLayoutWidget()
p1 = w1.addPlot(title="")
d1.addWidget(w1)
img = pg.ImageItem()
p1.addItem(img)
hist = pg.HistogramLUTItem()
hist.setImageItem(img)
hist.gradient.loadPreset('viridis')
w1.addItem(hist)


roi_items = [QGraphicsRectItem() for endpoint in endpoints]

for c, item in zip(['r', 'r'],roi_items):
    item.setPen(pg.mkPen(c, width=2))
    p1.addItem(item)


win.resize(900, 800)
win.show()
p1.setAspectLocked(True)
hist.setLevels(0,255)


def read_stream(buffer, exit_flag, endpoints):
    """
    Read images from the receiver zmq stream. Reuss sends
    multipart messages with [int64 frame_nr][float32 image]
    No data on size of image is provided so you have to set
    this in the configuration on top.
    """



    n_frames = 2
    contexts = [zmq.Context() for p in endpoints]
    sockets = [context.socket(zmq.SUB) for context in contexts]
    for endpoint, socket in zip(endpoints, sockets):
        socket.setsockopt(zmq.RCVTIMEO, timeout_ms)
        socket.setsockopt(zmq.RCVHWM, n_frames)
        socket.setsockopt(zmq.RCVBUF, n_frames*1024**2*np.dtype(dt).itemsize)
        socket.connect(endpoint)
        socket.setsockopt(zmq.SUBSCRIBE, b"")

    while not exit_flag.value:
        #Try to read an image, if timeout then try again
        for socket in sockets:
            try:
                msgs = socket.recv_multipart()
                if len(msgs) != 2:
                    pass #Dummy packet nothing to do 
                else:
                    #"rx_roi":[0, 1023, 0, 511]

                    header = json.loads(msgs[0])
                    # print(header)
                    print(f"Received frame: {header['frameNumber']}", end = '\r')
                    row = header['row']
                    tmp = np.frombuffer(msgs[1], dtype = dt).reshape(nrow, ncol)
                    with buffer.get_lock():
                        image = np.frombuffer(buffer.get_obj(), dtype=dt).reshape(
                            nrow*n_modules,ncol
                        )
                        np.copyto(image[nrow*row:nrow*(row+1),:], tmp)
                    with roi_buffer.get_lock():
                        roi = np.frombuffer(roi_buffer.get_obj(), dtype=np.int64)[row*4:(row+1)*4]
                        # roi[:] = header['rx_roi']
                        roi[0] = header['rx_roi'][0]
                        roi[1] = header['rx_roi'][2]+row*nrow
                        roi[2] = header['rx_roi'][1] - header['rx_roi'][0]
                        roi[3] = header['rx_roi'][3] - header['rx_roi'][2]

            except zmq.error.Again:
                pass

def update():
    with buffer.get_lock():
        image = np.frombuffer(buffer.get_obj(), dtype=dt).reshape(
                nrow*n_modules,ncol
            )
        
        img.setImage(image, autoRange = False, autoLevels = False, autoHistogramRange = False)
        np.copyto(data, image)
        

        for i, item in enumerate(roi_items):
            roi = roi_buffer[i*4:(i+1)*4]
            item.setRect(*roi)




def imageHoverEvent(event):
    global data
    if event.isExit():
        p1.setTitle("")
        return
    pos = event.pos()
    i, j = pos.y(), pos.x()
    i = int(np.clip(i, 0, data.shape[0] - 1))
    j = int(np.clip(j, 0, data.shape[1] - 1))
    
    val = data[i, j]
    ppos = img.mapToParent(pos)
    x, y = ppos.x(), ppos.y()
    p1.setTitle("pos: (%0.1f, %0.1f)  pixel: (%d, %d)  value: %.0f" % (x, y, i, j, val))

img.hoverEvent = imageHoverEvent

#Timer to update the image, this is separate from the receiving
#We could check and only update if we have a new image...
timer = QtCore.QTimer()
timer.timeout.connect(update)
timer.start(10)

# if __name__ == '__main__':


#Set some initial data
data = np.random.randint(0,4096, nrow*n_modules*ncol,dt).reshape(nrow*n_modules,ncol)

#This flag is used to inform the reader when to exit
exit_flag = mp.Value(ctypes.c_bool)
exit_flag.value = False 

#ROI buffer
roi_buffer = mp.Array(ctypes.c_int64, 4*n_modules)

#This has to match dt
buffer = mp.Array(ctypes_dt(dt), nrow*n_modules*ncol)
with buffer.get_lock():
    image = np.frombuffer(buffer.get_obj(), dtype=dt).reshape(
        nrow*n_modules,ncol
    )
    np.copyto(image, data)
reader = mp.Process(target=read_stream, args=[buffer, exit_flag,endpoints])
reader.start()

#Run the event loop for the GUI 
pg.exec()

#When the window is closed tell the reader loop to exit
exit_flag.value = True
reader.join()