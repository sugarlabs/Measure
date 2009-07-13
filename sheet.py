"""import gtk
from gtk import gdk
import pygtk
import matplotlib
matplotlib.use('GTKAgg')  # or 'GTK'
from matplotlib.backends.backend_gtk import FigureCanvasGTK as FigureCanvas
from matplotlib.figure import Figure
from numpy.random import random


class Sheet(gtk.DrawingArea):

    def __init__(self, filepath, journal):
        gtk.DrawingArea.__init__(self)
        
        self.filepath = filepath
        self.ji = journal
        self.numpy_arrays = []
        
        self.numRows = 0
        self.numCols = 0
        self.set_rows_and_cols()
        
        self.vbox = gtk.VBox(False, 8)
        
        self.sw = gtk.ScrolledWindow()
        self.sw.set_shadow_type(gtk.SHADOW_ETCHED_IN)
        self.sw.set_policy(gtk.POLICY_AUTOMATIC, gtk.POLICY_AUTOMATIC)
        
        model = self.create_model()
        self.treeview = gtk.TreeView(model)
        self.treeview.set_rules_hint(True)

        # matplotlib stuff
        fig = Figure(figsize=(6,4))
        self.canvas = FigureCanvas(fig)  # a gtk.DrawingArea        
        self.sw_canvas = gtk.ScrolledWindow()
        self.sw_canvas.set_shadow_type(gtk.SHADOW_ETCHED_IN)
        self.sw_canvas.set_policy(gtk.POLICY_AUTOMATIC, gtk.POLICY_AUTOMATIC)
        self.sw_canvas.add_with_viewport(self.canvas)
        self.vbox.pack_start(self.sw_canvas,True, True)
        
        
        ax = fig.add_subplot(111)
        self.line, = ax.plot(self.data[0,:], 'go')  # plot the first row
        self.treeview.connect('row-activated', self.plot_row)
        self.sw.add_with_viewport(self.treeview)
        
        label = gtk.Label('Double click a row to plot the data')
        self.vbox.pack_start(label, False, False)
        
        self.vbox.pack_start(self.sw, True, True)
        self.sw.set_size_request(100,100)
        self.treeview.set_size_request(100,100)
        
        self.add_columns()

        self.add_events(gdk.BUTTON_PRESS_MASK | gdk.KEY_PRESS_MASK | gdk.KEY_RELEASE_MASK)
        self.show_all()

        
        
        self.sw_canvas.set_size_request(100,100)


    def set_rows_and_cols(self):
        """Sets the rows and columns"""
        self.numRows = self.ji.get_number_of_records()
        self.numCols = self.ji.get_number_of_cols()
        

        
    def plot_row(self, treeview, path, view_column):
        ind, = path  # get the index into data
        points = self.data[ind,:]
        self.line.set_ydata(points)
        self.canvas.draw()


    def add_columns(self):
        for i in range(self.numCols):
            column = gtk.TreeViewColumn('%d'%i, gtk.CellRendererText(), text=i)
            self.treeview.append_column(column)


    def create_model(self):
        types = [float]*self.numCols
        store = gtk.ListStore(*types)

        for row in self.data:
            store.append(row)
        return store
"""

    def read_all_records(self):
        """Reads the complete csv file into the gtk Tree view"""
        self.data = self.ji.get_all_records()                   ##This, for now gets just all the numerical values
        
    
    def draw_dotted_plot(self):
        """Draws the dotted plot"""

