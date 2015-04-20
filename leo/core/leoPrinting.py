#@+leo-ver=5-thin
#@+node:ekr.20150419124739.1: * @file leoPrinting.py
'''
Support the commands in Leo's File:Print menu.
Adapted from printing plugin.
'''
import leo.core.leoGlobals as g
from leo.core.leoQt import QtWidgets

#@+others
#@+node:ekr.20150420120520.1: ** class PrintingController
class PrintingController:
    '''A class supporting the commands in Leo's File:Print menu.'''
    #@+others
    #@+node:ekr.20150419124739.6: *3* pr.__init__ & helpers
    def __init__ (self,c):
        '''Ctor for PrintingController class.'''
        self.c = c
        self.font_size = c.config.getString('printing-font-size') or '12'
        self.font_family = c.config.getString('printing-font-family') or 'DejaVu Sans Mono'
        self.stylesheet = self.construct_stylesheet()
    #@+node:ekr.20150419124739.8: *4* pr.construct stylesheet
    def construct_stylesheet(self):
        '''Return the Qt stylesheet to be used for printing.'''
        family,size = self.font_family,self.font_size
        table = (
            'h1 {font-family: %s}' % (family),
            'pre {font-family: %s; font-size: %spx}' % (family,size),
        )
        return '\n'.join(table)
    #@+node:ekr.20150420073407.1: *4* pr.getPublicCommands
    def getPublicCommands (self):
        '''Add this class's commands to c.commandsDict.'''
        self.c.commandsDict.update({
        # Preview.
        'preview-body':         self.preview_body,
        'preview-html':         self.preview_html,
        'preview-node':         self.preview_node,
        'preview-tree-bodies':  self.preview_tree_bodies,
        'preview-tree-html':    self.preview_tree_html,
        'preview-tree-nodes':   self.preview_tree_nodes,
        # Preview marked.
        'preview-marked-bodies':self.preview_marked_bodies,
        'preview-marked-html':  self.preview_marked_html,
        'preview-marked-nodes': self.preview_marked_nodes,
        # Selected node/tree.
        'print-body':           self.print_body,
        'print-html':           self.print_html,
        'print-node':           self.print_node,
        'print-tree-bodies':    self.print_tree_bodies,
        'print-tree-html':      self.print_tree_html,
        'print-tree-nodes':     self.print_tree_nodes,
        # Marked nodes.
        'print-marked-bodies':  self.print_marked_bodies,
        'print-marked-html':    self.print_marked_html,
        'print-marked-nodes':   self.print_marked_nodes,
    })
    #@+node:ekr.20150420072955.1: *3* pr.Doc constructors
    #@+node:ekr.20150419124739.11: *4* pr.complex document
    def complex_document(self, nodes, heads=False):
        '''Create a complex document.'''
        doc = QtWidgets.QTextDocument()
        doc.setDefaultStyleSheet(self.stylesheet)
        contents = ''
        for n in nodes:
            if heads:
                contents += '<h1>%s</h1>\n' % (self.sanitize_html(n.h))
            contents += '<pre>%s</pre>\n' % (self.sanitize_html(n.b))
        doc.setHtml(contents)
        return doc
    #@+node:ekr.20150419124739.9: *4* pr.document
    def document(self, text, head=None):
        '''Create a Qt document.'''
        doc = QtWidgets.QTextDocument()
        doc.setDefaultStyleSheet(self.stylesheet)
        text = self.sanitize_html(text)
        if head:
            head = self.sanitize_html(head)
            contents = "<h1>%s</h1>\n<pre>%s</pre>" % (head, text)
        else:
            contents = "<pre>%s<pre>" % text
        doc.setHtml(contents)
        return doc
    #@+node:ekr.20150419124739.10: *4* pr.html_document
    def html_document(self, text):
        '''Create an HTML document.'''
        doc = QtWidgets.QTextDocument()
        doc.setDefaultStyleSheet(self.stylesheet)
        doc.setHtml(text)
        return doc
    #@+node:ekr.20150420073201.1: *3* pr.Helpers
    #@+node:ekr.20150419124739.15: *4* pr.getBodies
    def getBodies(self,p):
        '''Return the entire script at node p.'''
        if 1:
            return '\n'.join([p.b for p in p.self_and_subtree()])
        else:
            return g.getScript(self.c,p,
                useSelectedText=False,
                useSentinels=False)
    #@+node:ekr.20150420085602.1: *4* pr.getNodes
    def getNodes(self,p):
        '''Return the entire script at node p.'''
        result = [p.b]
        for p in p.subtree():
            result.extend(['','Node: %s' % (p.h),''])
            result.append(p.b)
        return '\n'.join(result)

        
    #@+node:ekr.20150419124739.14: *4* pr.sanitize html
    def sanitize_html(self, html):
        '''Generate html escapes.'''
        return html.replace('&', '&amp;').replace('<', '&lt;').replace('>', '&gt;')
    #@+node:ekr.20150420081215.1: *3* pr.Preview
    #@+node:ekr.20150419124739.21: *4* pr.preview_body
    def preview_body (self,event=None):
        '''Preview the body of the selected node.'''
        doc = self.document(self.c.p.b)
        self.preview_doc(doc)
    #@+node:ekr.20150419124739.19: *4* pr.preview_html
    def preview_html (self,event=None):
        '''Preview the body of the selected text as html (rich text)'''
        doc = self.html_document(self.c.p.b)
        self.preview_doc(doc)
    #@+node:ekr.20150419124739.31: *4* pr.preview_marked_bodies
    def preview_marked_bodies (self,event=None):
        '''Preview the bodies of the marked nodes.'''
        nodes = [p.v for p in self.c.all_positions() if p.isMarked()]
        doc = self.complex_document(nodes)
        self.preview_doc(doc)
    #@+node:ekr.20150420081906.1: *4* pr.preview_marked_html
    def preview_marked_html (self,event=None):
        '''Preview the html in the bodies of the marked nodes..'''
        nodes = [p.v for p in self.c.all_positions() if p.isMarked()]
        s = '\n'.join([z.b for z in nodes])
        doc = self.html_document(s)
        self.preview_doc(doc)
    #@+node:ekr.20150419124739.33: *4* pr.preview_marked_nodes
    def preview_marked_nodes (self,event=None):
        '''Preview the marked nodes.'''
        nodes = [p.v for p in self.c.all_positions() if p.isMarked()]
        doc = self.complex_document(nodes,heads=True)
        self.preview_doc(doc)
    #@+node:ekr.20150419124739.23: *4* pr.preview_node
    def preview_node (self,event=None):
        '''Preview the selected node.'''
        p = self.c.p
        doc = self.document(p.b,head=p.h)
        self.preview_doc(doc)
    #@+node:ekr.20150419124739.26: *4* pr.preview_tree_bodies
    def preview_tree_bodies (self,event=None):
        '''Preview the bodies in the selected tree.'''
        doc = self.document(self.getBodies(self.c.p))
        self.preview_doc(doc)
    #@+node:ekr.20150419124739.28: *4* pr.preview_tree_nodes
    def preview_tree_nodes (self,event=None):
        '''Preview the entire tree.'''
        p = self.c.p
        doc = self.document(self.getNodes(p),head=p.h)
        self.preview_doc(doc)
    #@+node:ekr.20150420081923.1: *4* pr_preview_tree_html
    def preview_tree_html (self,event=None):
        '''Preview all the bodies of the selected node as html (rich text)'''
        doc = self.html_document(self.getBodies(self.c.p))
        self.preview_doc(doc)
    #@+node:ekr.20150420073128.1: *3* pr.Print
    #@+node:ekr.20150419124739.20: *4* pr.print_body
    def print_body (self,event=None):
        '''Print the selected node's body'''
        doc = self.document(self.c.p.b)
        self.print_doc(doc)
    #@+node:ekr.20150419124739.18: *4* pr.print_html
    def print_html (self,event=None):
        '''Print the selected node body as html (rich text)'''
        doc = self.html_document(self.c.p.b)
        self.print_doc(doc)
    #@+node:ekr.20150419124739.30: *4* pr.print_marked_bodies
    def print_marked_bodies (self,event=None):
        '''Print the body text of marked nodes.'''
        nodes = [p.v for p in self.c.all_positions() if p.isMarked()]
        doc = self.complex_document(nodes)
        self.print_doc(doc)
    #@+node:ekr.20150420085054.1: *4* pr.print_marked_html
    def print_marked_html (self,event=None):
        '''Print the bodies of all marked nodes as html.'''
        nodes = [p.v for p in self.c.all_positions() if p.isMarked()]
        s = '\n'.join([z.b for z in nodes])
        doc = self.html_document(s)
        self.print_doc(doc)
    #@+node:ekr.20150419124739.32: *4* pr.print_marked_nodes
    def print_marked_nodes (self,event=None):
        '''Print all the marked nodes'''
        nodes = [p.v for p in self.c.all_positions() if p.isMarked()]
        doc = self.complex_document(nodes, heads=True)
        self.print_doc(doc)
    #@+node:ekr.20150419124739.22: *4* pr.print_node
    def print_node (self,event=None):
        '''Print the selected node '''
        doc = self.document(self.c.p.b,head=self.c.p.h)
        self.print_doc(doc)
    #@+node:ekr.20150419124739.25: *4* pr.print_tree_bodies
    def print_tree_bodies (self,event=None):
        '''Print all the bodies in the selected tree.'''
        doc = self.document(self.getBodies(self.c.p))
        self.print_doc(doc)
    #@+node:ekr.20150420084948.1: *4* pr.print_tree_html
    def print_tree_html (self,event=None):
        '''Print the bodies of all the marked nodes as html.'''
        nodes = [p.v for p in self.c.all_positions() if p.isMarked()]
        s = '\n'.join([z.b for z in nodes])
        doc = self.html_document(s)
        self.print_doc(doc)
    #@+node:ekr.20150419124739.27: *4* pr.print_tree_nodes
    def print_tree_nodes (self,event=None):
        '''Print all the nodes of the selected tree.'''
        doc = self.document(self.getNodes(self.c.p),head=self.c.p.h)
        self.print_doc(doc)
    #@+node:ekr.20150419124739.7: *3* pr.Top level
    #@+node:ekr.20150419124739.12: *4* pr.print_doc
    def print_doc(self, doc):
        '''Print the document.'''
        dialog = QtWidgets.QPrintDialog()
        if dialog.exec_() == QtWidgets.QDialog.Accepted:
            doc.print_(dialog.printer())
    #@+node:ekr.20150419124739.13: *4* pr.preview_doc
    def preview_doc(self, doc):
        '''Preview the document.'''
        dialog = QtWidgets.QPrintPreviewDialog()
        dialog.setSizeGripEnabled(True)
        dialog.paintRequested.connect(doc.print_)
        dialog.exec_()
    #@-others
#@-others
#@@language python
#@@tabwidth -4
#@-leo
