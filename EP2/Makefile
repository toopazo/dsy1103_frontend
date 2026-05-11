MAIN = main
BUILD = build

.PHONY: all clean

all:
	mkdir -p $(BUILD)
	pdflatex -output-directory=$(BUILD) $(MAIN).tex
	pdflatex -output-directory=$(BUILD) $(MAIN).tex

clean:
	rm -rf $(BUILD)
