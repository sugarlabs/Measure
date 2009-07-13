"""import gtk
from matplotlib.toolkits.gtktools import rec2gtk
import matplotlib.mlab as mlab
from pylab import figure, show, plot
from matplotlib.figure import Figure
from numpy import arange
from matplotlib.numerix import sin,pi
from matplotlib.backends.backend_gtk import FigureCanvasGTK as FigureCanvas
from matplotlib.backends.backend_gtk import NavigationToolbar2GTK as NavigationToolbar
import gtk

from gettext import gettext as _
import config  	#This has all the globals


class Graphs(gtk.DrawingArea):

    def __init__(self):
        gtk.DrawingArea.__init__(self)

        #d = mlab.csv2rec('myfile.csv')
        #print type(d)
        """
        t = arange(0,10,1)
        s= sin(2*pi*t)
        plot(t,s)
        show()
        """

        fig = Figure(figsize=(5,4), dpi=100)
        ax = fig.add_subplot(111)
        t = arange(0.0,3.0,1)
        s =[1,2,3]
        s2=[9,8,7]
        ax.plot(t,s,t, s2)
        canvas = FigureCanvas(fig)  # a gtk.DrawingArea
        self.vbox1=gtk.VBox()
        self.vbox1.pack_start(canvas)
        toolbar = NavigationToolbar(canvas, None)
        self.vbox1.pack_start(toolbar, False, False)

        self.vbox1.show_all()

    """
    
